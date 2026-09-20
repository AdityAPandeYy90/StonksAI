import requests
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0'}
# We test with the warehouse-id of Tata Steel: 6599238
url = 'https://www.screener.in/api/company/6599238/peers/'
r = requests.get(url, headers=headers)
soup = BeautifulSoup(r.content, 'html.parser')

print("Peers Table Rows:")
for tr in soup.find_all('tr')[:5]:
    cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
    print(cells)
