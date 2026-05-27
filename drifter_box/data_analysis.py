import pandas as pd

# Load species catalog
df = pd.read_csv('speciescatalog.csv')

# Basic analysis
print("Total records:", len(df))
print("Species diversity:", df['species'].nunique())
print("Average occurrences per species:", df.groupby('species').size().mean())

# Example: save summary
summary = df.groupby('species').size().reset_index(name='count')
summary.to_csv('species_summary.csv', index=False)
print("Summary saved to species_summary.csv")
