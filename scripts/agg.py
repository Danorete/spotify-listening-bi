import pandas as pd
df=pd.read_csv("streams_clean.csv",parse_dates=["date"])
d=pd.read_csv("daily_summary.csv",parse_dates=["date"]).set_index("date")
full=pd.date_range(d.index.min(),d.index.max())
missing=full.difference(d.index)
print("missing days",len(missing))
# longest gaps
s=pd.Series(missing); g=(s.diff()!=pd.Timedelta(days=1)).cumsum()
for _,x in s.groupby(g): 
    if len(x)>=3: print(x.iloc[0].date(),"to",x.iloc[-1].date(),len(x),"days")
print(d.loc["2025-11-20":"2026-01-10","hours"].to_string())
# aggregates for publishing
df.groupby(["weekday","weekday_num","hour"]).agg(streams=("track","size"),hours=("minutes_played",lambda s:s.sum()/60),skips=("is_skip","sum")).reset_index().to_csv("hour_weekday_heatmap.csv",index=False)
df.groupby(["year_month","artist"]).agg(streams=("track","size"),hours=("minutes_played",lambda s:s.sum()/60),skips=("is_skip","sum")).reset_index().to_csv("artist_by_month.csv",index=False)
df.groupby(["artist","track"]).agg(streams=("track","size"),hours=("minutes_played",lambda s:s.sum()/60),skips=("is_skip","sum"),full_listens=("is_full_listen","sum")).reset_index().to_csv("track_summary.csv",index=False)
print("skip rate by hour:");print(df.groupby("hour").is_skip.mean().round(2).to_string())
