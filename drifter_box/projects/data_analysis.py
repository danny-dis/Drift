# Data analysis script for species catalog
import pandas as pd
import glob

def load_data():
    files = glob.glob('data/*.csv')
    df = pd.concat([pd.read_csv(f) for f in files])
    return df

if __name__ == '__main__':
    df = load_data()
    print(df.head())
