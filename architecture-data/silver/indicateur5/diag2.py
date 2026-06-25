import pandas as pd
df = pd.read_parquet(r'C:\Users\rayan\OneDrive\Documents\architecture-data\architecture-data\brute\Indicateurs de logement\dvf2.parquet')
df.columns = df.columns.str.strip()

m = (df['type_local']=='Appartement') & (df['nature_mutation']=='Vente') & (df['code_commune'].astype(str)=='75101')
sub = df[m].copy()
sub['vf'] = pd.to_numeric(sub['valeur_fonciere'].astype(str).str.replace(',','.'), errors='coerce')
sub['sf'] = pd.to_numeric(sub['surface_reelle_bati'].astype(str).str.replace(',','.'), errors='coerce')

print("Total lignes appart-vente 75101 :", len(sub))
print("id_mutation uniques            :", sub['id_mutation'].nunique())
print("lignes / mutation              :", round(len(sub)/sub['id_mutation'].nunique(),2))

print("\n=== repartition lignes par mutation ===")
print(sub.groupby('id_mutation').size().value_counts().head())

sub_lot = sub[(sub['vf']>0)&(sub['sf']>0)]
sub_lot = sub_lot[(sub_lot['vf']/sub_lot['sf']).between(2000,40000)]
print("\nprix median PAR LOT      :", round((sub_lot['vf']/sub_lot['sf']).median()))

mut = sub.groupby('id_mutation').agg(vf=('vf','first'), sf=('sf','sum')).reset_index()
mut['pm2'] = mut['vf']/mut['sf']
mut = mut[mut['pm2'].between(2000,40000)]
print("prix median PAR MUTATION :", round(mut['pm2'].median()))
print("nb mutations valides     :", len(mut))

print("\n=== une valeur_fonciere repetee sur combien de lignes ? ===")
print(sub['vf'].value_counts().head())