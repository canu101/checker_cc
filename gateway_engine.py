import asyncio
import logging
import requests
import json
import re
import time
from database import DatabaseManager
from config import WOOCOMMERCE_SITE_PASSED, WOOCOMMERCE_SITE_OTP

logger = logging.getLogger(__name__)


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

        # First check gateway-specific patterns if available
        if gw:
            success_pat = gw.get('success_pattern', '').strip()
            decline_pat = gw.get('decline_pattern', '').strip()
            error_pat = gw.get('error_pattern', '').strip()

            if success_pat and re.search(success_pat, raw_text, re.IGNORECASE):
                result.update({'category': 'approved_charged', 'status_text': 'APPROVED', 'reason': 'Success - Pattern Match'})
                return result
            if decline_pat and re.search(decline_pat, raw_text, re.IGNORECASE):
                result.update({'category': 'declined', 'status_text': 'DECLINED', 'reason': 'Declined - Pattern Match'})
                return result
            if error_pat and re.search(error_pat, raw_text, re.IGNORECASE):
                result.update({'category': 'error', 'status_text': 'ERROR', 'reason': 'Error - Pattern Match'})
                return result

        # Try JSON parsing for structured responses
        try:
            data = json.loads(raw_text)
            
            # Check for error field (common in Stripe-like APIs)
            if 'error' in data:
                err = data['error']
                code = err.get('decline_code', '')
                msg = err.get('message', 'Declined')
                if code == 'insufficient_funds':
                    result.update({'category': 'approved_insufficient', 'status_text': 'APPROVED', 'reason': f'Insufficient Funds - {msg}'})
                elif code in ['card_declined', 'incorrect_cvc', 'expired_card']:
                    result.update({'category': 'declined', 'status_text': 'DECLINED', 'reason': msg})
                else:
                    result.update({'category': 'declined', 'status_text': 'DECLINED', 'reason': msg})
                return result
            
            # Check for success indicators
            if data.get('status') == 'succeeded':
                amt = data.get('amount', 0)
                curr = data.get('currency', 'usd').upper()
                result.update({'category': 'approved_charged', 'status_text': 'APPROVED', 'reason': 'Payment Successful', 'amount': f"{amt/100:.2f} {curr}"})
                return result
            
            if data.get('status') == 'requires_action':
                result.update({'category': 'auth_required', 'status_text': 'APPROVED', 'reason': '3D Secure / OTP Required', 'requires_3ds': True})
                return result
            
            if data.get('status') == 'requires_capture':
                result.update({'category': 'approved_auth_only', 'status_text': 'APPROVED', 'reason': 'Authorized (Not Captured)'})
                return result

            # Check for other common success fields
            if data.get('success') == True or data.get('approved') == True:
                result.update({'category': 'approved_charged', 'status_text': 'APPROVED', 'reason': 'Success'})
                return result
            
            if data.get('response') == 'approved':
                result.update({'category': 'approved_charged', 'status_text': 'APPROVED', 'reason': 'Approved'})
                return result
                
        except json.JSONDecodeError:
            pass  # Not JSON, continue to text analysis
        except Exception as e:
            logger.warning(f"JSON parse error: {e}")

        # Fallback: text-based analysis
        text_lower = raw_text.lower()
        
        # Check for approval keywords
        if re.search(r'\b(approved|success|succeeded|authorized)\b', text_lower):
            if 'insufficient' in text_lower or 'funds' in text_lower:
                result.update({'category': 'approved_insufficient', 'status_text': 'APPROVED', 'reason': 'Insufficient Funds'})
            else:
                result.update({'category': 'approved_charged', 'status_text': 'APPROVED', 'reason': 'Success'})
            return result
        
        # Check for decline keywords
        if re.search(r'\b(declined|rejected|failure|failed)\b', text_lower):
            result.update({'category': 'declined', 'status_text': 'DECLINED', 'reason': 'Declined'})
            return result
        
        # Check for error keywords
        if re.search(r'\b(error|invalid|unauthorized)\b', text_lower):
            result.update({'category': 'error', 'status_text': 'ERROR', 'reason': 'Error in response'})
            return result

        return result

    def _is_woocommerce_gateway(self, gw):
        """Detect if a gateway is WooCommerce-based by its endpoint or display name."""
        endpoint = (gw.get('api_endpoint') or '').lower()
        name = (gw.get('display_name') or '').lower()
        woo_markers = ['woocommerce', 'woo', '?wc-ajax=', 'wp-json/wc/', 'add-to-cart', 'checkout']
        return any(m in endpoint or m in name for m in woo_markers)

    async def check_single(self, gateway_id, card_data, proxy_data=None):
        gw = self.db.get_gateway_by_id(gateway_id)
        if not gw:
            return {'success': False, 'error': 'Gateway not found', 'category': 'error'}

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
            headers = json.loads(gw['headers_json']) if gw['headers_json'] else {}
            body = self.format_request(gw['body_template'], card_data)
            timeout = int(gw['timeout_seconds'] or 30)

            # Resolve the target URL: prefer WooCommerce env vars when applicable
            if self._is_woocommerce_gateway(gw):
                # Use OTP/3DS URL for gateways that require 3DS, otherwise use the passed URL
                woo_url = WOOCOMMERCE_SITE_OTP if gw.get('requires_3ds') else WOOCOMMERCE_SITE_PASSED
                url = woo_url if woo_url else gw['api_endpoint']
                logger.info(f"WooCommerce gateway detected — using URL: {url[:60]}")
            else:
                url = gw['api_endpoint']

            if not url:
                return {
                    'success': False,
                    'error': 'No endpoint URL configured for this gateway',
                    'category': 'error',
                    'reason': 'Missing endpoint URL',
                    'elapsed': f"{round(time.time() - start, 2)}s",
                    'raw': ''
                }

            headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

            if method == 'GET':
                resp = await loop.run_in_executor(
                    None,
                    lambda: requests.get(url, headers=headers, proxies=proxy, timeout=timeout)
                )
            else:
                # Check Content-Type header to decide how to send body
                content_type = headers.get('Content-Type', '').lower()
                if 'application/json' in content_type:
                    # Try to parse body as JSON and send with json= parameter
                    try:
                        json_body = json.loads(body)
                        resp = await loop.run_in_executor(
                            None,
                            lambda: requests.post(url, json=json_body, headers=headers, proxies=proxy, timeout=timeout)
                        )
                    except json.JSONDecodeError:
                        # Invalid JSON in body, send as raw data
                        resp = await loop.run_in_executor(
                            None,
                            lambda: requests.post(url, data=body, headers=headers, proxies=proxy, timeout=timeout)
                        )
                else:
                    # Send as form/data
                    resp = await loop.run_in_executor(
                        None,
                        lambda: requests.post(url, data=body, headers=headers, proxies=proxy, timeout=timeout)
                    )

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
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Gateway {gateway_id} connection error: {e}")
            if proxy_id:
                self.db.increment_proxy_fail(proxy_id)
            return {
                'success': False,
                'proxy_id': proxy_id,
                'error': f"Connection error: {e}",
                'category': 'error',
                'reason': 'فشل الاتصال بالبوابة — تحقق من الرابط أو البروكسي',
                'elapsed': f"{round(time.time() - start, 2)}s",
                'raw': ''
            }
        except requests.exceptions.Timeout as e:
            logger.error(f"Gateway {gateway_id} timeout: {e}")
            if proxy_id:
                self.db.increment_proxy_fail(proxy_id)
            return {
                'success': False,
                'proxy_id': proxy_id,
                'error': f"Timeout: {e}",
                'category': 'error',
                'reason': 'انتهت مهلة الاتصال — حاول مجدداً',
                'elapsed': f"{round(time.time() - start, 2)}s",
                'raw': ''
            }
        except Exception as e:
            logger.error(f"Gateway {gateway_id} unexpected error: {e}", exc_info=True)
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
