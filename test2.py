import pandas as pd

df = pd.read_csv("DS_FILOSOFI_CC_data.csv", sep=None, engine="python")

paris_revenus = df[
    (df['GEO'].astype(str).str.match(r'^751\d{2}$')) &
    (df['FILOSOFI_MEASURE'] == 'MED_SL')
][['GEO', 'OBS_VALUE']].rename(columns={
    'GEO': 'code_arrondissement',
    'OBS_VALUE': 'revenu_median'
})

print(paris_revenus.sort_values('code_arrondissement'))