import json,glob,sys,os
import pandas as pd
src,out=sys.argv[1],sys.argv[2]
rows=[]
for f in sorted(glob.glob(os.path.join(src,"StreamingHistory_music_*.json"))):
    rows+=json.load(open(f))
df=pd.DataFrame(rows).rename(columns={"endTime":"end_time_utc","artistName":"artist","trackName":"track","msPlayed":"ms_played"})
t=pd.to_datetime(df.end_time_utc,utc=True).dt.tz_convert("America/New_York")
df["end_time_local"]=t.dt.strftime("%Y-%m-%d %H:%M")
df["date"]=t.dt.date; df["year_month"]=t.dt.strftime("%Y-%m")
df["hour"]=t.dt.hour; df["weekday"]=t.dt.day_name(); df["weekday_num"]=t.dt.weekday
df["minutes_played"]=(df.ms_played/60000).round(2)
df["is_skip"]=(df.ms_played<30000).astype(int)   # Spotify counts a stream at 30s
df["is_full_listen"]=(df.ms_played>=120000).astype(int)
before=len(df); df=df.drop_duplicates(["end_time_utc","artist","track","ms_played"]); print("dupes dropped",before-len(df))
df=df.sort_values("end_time_utc").reset_index(drop=True)
df.to_csv(os.path.join(out,"streams_clean.csv"),index=False)
a=df.groupby("artist").agg(streams=("track","size"),hours=("ms_played",lambda s:round(s.sum()/3.6e6,2)),
  skips=("is_skip","sum"),tracks=("track","nunique"),first=("date","min"),last=("date","max")).reset_index()
a["skip_rate"]=(a.skips/a.streams).round(3); a.sort_values("hours",ascending=False).to_csv(os.path.join(out,"artist_summary.csv"),index=False)
d=df.groupby("date").agg(streams=("track","size"),hours=("ms_played",lambda s:round(s.sum()/3.6e6,2)),skips=("is_skip","sum")).reset_index()
d.to_csv(os.path.join(out,"daily_summary.csv"),index=False)
print(len(df),"streams;",df.artist.nunique(),"artists;",df.date.min(),"to",df.date.max(),"; days active",len(d))
print(df.groupby("year_month").ms_played.sum().div(3.6e6).round(0).to_string())
print(df.groupby("hour").size().to_string())
