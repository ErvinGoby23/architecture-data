import pandas as pd

df = pd.read_csv("dvf.csv", nrows=0)
print(df.columns.tolist())
print("done")