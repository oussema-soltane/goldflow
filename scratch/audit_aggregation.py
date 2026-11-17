import pandas as pd

m5 = pd.read_csv('data/raw/XAUUSD_M5_raw.csv')
m5['time'] = pd.to_datetime(m5['time'], utc=True)
m5['time_15m'] = m5['time'].dt.floor('15min')

grp = m5.groupby('time_15m')
counts = grp.size()

partial_1 = counts[counts == 1]
partial_2 = counts[counts == 2]

print('Total M5 rows:', len(m5))
print('Total 15m groups:', len(counts))
print('Groups with 3 M5 bars:', (counts == 3).sum())
print('Groups with 2 M5 bars:', len(partial_2))
print('Groups with 1 M5 bar:', len(partial_1))

# Check distribution of hours and days for partials
print('\nPartial 1-bar intervals distribution by hour (UTC):')
print(partial_1.index.hour.value_counts().to_dict())

print('\nPartial 2-bar intervals distribution by hour (UTC):')
print(partial_2.index.hour.value_counts().to_dict())

print('\nSample 1-bar intervals:')
for t in partial_1.index[:10]:
    sub = m5[m5['time_15m'] == t]
    times_str = ', '.join(sub['time'].dt.strftime('%H:%M'))
    print(f"  {t} ({t.strftime('%A')}, {t.hour:02d}:{t.minute:02d} UTC): {times_str}")

print('\nSample 2-bar intervals:')
for t in partial_2.index[:10]:
    sub = m5[m5['time_15m'] == t]
    times_str = ', '.join(sub['time'].dt.strftime('%H:%M'))
    print(f"  {t} ({t.strftime('%A')}, {t.hour:02d}:{t.minute:02d} UTC): {times_str}")

