import pandas as pd
import sys

def main(csv_path):
    df = pd.read_csv(csv_path)
    print(f"Total species: {len(df)}")
    print(f"Unique genera: {df['genus'].nunique()}")
    print("\nSpecies count per genus:")
    print(df['genus'].value_counts())

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fungi_analysis.py <path_to_csv>")
    else:
        main(sys.argv[1])
