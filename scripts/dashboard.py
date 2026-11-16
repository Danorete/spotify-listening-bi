"""Build the tables Tableau reads, from data/streams_clean.csv.

Usage: python scripts/dashboard.py <data_dir>
"""
import sys, os
import pandas as pd

D = sys.argv[1] if len(sys.argv) > 1 else "data"
TOP_N = 50
OTHER = "All other artists"

df = pd.read_csv(f"{D}/streams_clean.csv", parse_dates=["date"])
df["month_start"] = df.date.dt.to_period("M").dt.start_time.dt.strftime("%Y-%m-%d")
df["date"] = df.date.dt.strftime("%Y-%m-%d")

# Monthly totals
m = df.groupby(["year_month", "month_start"]).agg(
    streams=("track", "size"), hours=("ms_played", "sum"), skips=("is_skip", "sum")).reset_index()
m["hours"] = (m.hours / 3.6e6).round(2)
m[["year_month", "streams", "hours", "skips", "month_start"]].to_csv(f"{D}/monthly_summary.csv", index=False)

# Top artists by hours. "Unknown Artist" is not a real artist, so it falls into the other bucket.
hours = df[df.artist != "Unknown Artist"].groupby("artist").ms_played.sum()
top = set(hours.nlargest(TOP_N).index)
df["artist_group"] = df.artist.where(df.artist.isin(top), OTHER)

# Main table: one row per artist, date and hour
grain = ["artist_group", "date", "year_month", "weekday", "weekday_num", "hour", "month_start"]
d = df.groupby(grain).agg(streams=("track", "size"), hours=("ms_played", "sum"), skips=("is_skip", "sum")).reset_index()
d["hours"] = (d.hours / 3.6e6).round(4)
d = d.rename(columns={"artist_group": "artist"})
d = d[["artist", "date", "year_month", "weekday", "weekday_num", "hour", "streams", "hours", "skips", "month_start"]]
d = d.sort_values(["date", "hour", "artist"]).reset_index(drop=True)
d.to_csv(f"{D}/dashboard_artist_date_hour.csv", index=False)

# Most played song per top artist (ties broken by hours played)
t = df[df.artist.isin(top)].groupby(["artist", "track"]).agg(plays=("track", "size"), ms=("ms_played", "sum")).reset_index()
best = t.sort_values(["artist", "plays", "ms"], ascending=[True, False, False]).drop_duplicates("artist")
s = pd.concat([pd.DataFrame([{"artist": OTHER, "top_song": "Varies (many artists)", "top_song_plays": 0}]),
               best.rename(columns={"track": "top_song", "plays": "top_song_plays"})[["artist", "top_song", "top_song_plays"]]])
s.to_csv(f"{D}/artist_top_song.csv", index=False)

# Same main table with the top song joined on, for workbooks that want one flat source
d.merge(s, on="artist", how="left").to_csv(f"{D}/dashboard_artist_date_hour_with_top_song.csv", index=False)

print(f"dashboard tables: {len(d):,} rows, {len(top)} top artists, {len(m)} months")
