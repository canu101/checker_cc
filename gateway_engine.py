import asyncio
import requests
import json
import re
import time
from database import DatabaseManager


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

    async def check_single(self, gateway_id, card_data, proxy_data=None):
        if isinstance(gateway_id, dict):
            gw = gateway_id
        else:
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
