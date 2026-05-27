import requests

class BINService:
    def __init__(self):
        self.cache = {}

    def lookup(self, card_number: str):
        bin_num = str(card_number)[:6]
        if bin_num in self.cache:
            return self.cache[bin_num]

        try:
            resp = requests.get(f"https://lookup.binlist.net/{bin_num}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                result = {
                    'bank': data.get('bank', {}).get('name', 'Unknown'),
                    'country': data.get('country', {}).get('name', 'Unknown'),
                    'flag': data.get('country', {}).get('emoji', ''),
                    'scheme': (data.get('scheme') or 'Unknown').upper(),
                    'type': (data.get('type') or 'Unknown').upper(),
                    'brand': (data.get('brand') or '').upper(),
                    'prepaid': 'Yes' if data.get('prepaid') else 'No'
                }
                self.cache[bin_num] = result
                return result
        except Exception as e:
            print(f"BIN Lookup Error: {e}")

        return {
            'bank': 'Unknown', 'country': 'Unknown', 'flag': '',
            'scheme': 'Unknown', 'type': 'Unknown', 'brand': '', 'prepaid': 'No'
        }
