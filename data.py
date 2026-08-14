import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random

data_list = []
page = 1
total_annonces = 0

print("Bismillah... L-code bda. Db wkha tqte3 l-connexion, maghadich ystselem 7ta yjme3 kolchi!")

while True:
    print(f"-> Jari istikhraj l-data mn l-page {page}...")
    
    if page == 1:
        url = "https://www.mubawab.ma/fr/sc/appartements-a-vendre"
    else:
        url = f"https://www.mubawab.ma/fr/sc/appartements-a-vendre:p:{page}"
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # ---------------------------------------------------------
    # SYSTEME DYAL RETRY: Ghadi ybqa y7awel 5 d l-mrat f nfs l-page ila kan mouchkil
    # ---------------------------------------------------------
    page_mzyana = False
    mo7awalat = 0
    max_mo7awalat = 5
    
    while not page_mzyana and mo7awalat < max_mo7awalat:
        try:
            response = requests.get(url, headers=headers, timeout=20) # Zedt l-waqt l 20 taniya
            
            if response.status_code == 200:
                page_mzyana = True # L-page t7ellat mzyan, nkhurjou mn l-mo7awalat
            else:
                mo7awalat += 1
                print(f"  [!] L-sit 3tana erreur {response.status_code}. Ntsnaw 5 tawanio w n3awdo... ({mo7awalat}/{max_mo7awalat})")
                time.sleep(5)
                
        except requests.exceptions.RequestException as e:
            mo7awalat += 1
            print(f"  [!] Connexion t9ilat aw tqet3at f l-page {page}. Ntsnaw 10 tawanio w n3awdo... ({mo7awalat}/{max_mo7awalat})")
            time.sleep(10) # Kan-tsnaw l-internet trje3
            
    # Ila drna 5 d l-mo7awalat w walo, y3ni l-sit sala aw t7besna b sifa niha2iya
    if not page_mzyana:
        print(f"\n!! Wqefna f l-page {page} b3d 5 d l-mo7awalat. L-scraping ghadi ykml db l-fichier.")
        break
    # ---------------------------------------------------------
        
    soup = BeautifulSoup(response.text, 'html.parser')
    annonces = soup.find_all('div', class_='listingBox')
    
    if len(annonces) == 0:
        print("\n*** Salaw l-pages! Jme3na l-data d l-Moghrib KAMLA. ***")
        break
        
    for annonce in annonces:
        try:
            titre_element = annonce.find('h2', class_='listingTit')
            prix_element = annonce.find('span', class_='priceTag')
            loc_element = annonce.find('i', class_='icon-location')
            
            titre = titre_element.text.strip() if titre_element else None
            prix = prix_element.text.strip() if prix_element else None
            localisation = loc_element.parent.text.strip().replace('\n', ' ').replace('\t', '') if loc_element else None
            
            details_element = annonce.find('div', class_='adDetails')
            details = " ".join(details_element.text.split()) if details_element else None
            
            if titre and prix:
                data_list.append({
                    'Titre': titre,
                    'Prix': prix,
                    'Localisation': localisation,
                    'Details': details
                })
                total_annonces += 1
                
        except Exception as e:
            continue
            
    time.sleep(random.uniform(1.5, 3.5))
    page += 1

# Mli ytsalaw ga3 l-pages mzyan, 3ad n-creeyiou l-fichier l-kamel
if data_list:
    print(f"\nJari isha2 l-fichier CSV... (Total d l-annonces f l-Moghrib: {total_annonces})")
    df = pd.DataFrame(data_list)
    nom_fichier = "maisonlux_maroc_complet.csv"
    df.to_csv(nom_fichier, index=False, encoding='utf-8-sig') 
    print(f"=> NADI! L-fichier '{nom_fichier}' wajed w fih l-data mkmoula!")
else:
    print("Mouchkil: ma tjem3at 7ta data.")