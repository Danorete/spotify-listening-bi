import sys,os,pandas as pd,numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch
D,O=sys.argv[1],sys.argv[2]
SURF="#fcfcfb";INK="#0b0b0b";INK2="#52514e";MUT="#898781";GRID="#e1e0d9";BLUE="#2a78d6";DEEP="#0d366b";ORG="#eb6834"
seq=LinearSegmentedColormap.from_list("b",["#cde2fb","#86b6ef","#3987e5","#256abf","#104281","#0d366b"])
plt.rcParams.update({"font.family":"DejaVu Sans","axes.facecolor":SURF,"figure.facecolor":SURF,"text.color":INK,
 "axes.edgecolor":GRID,"axes.labelcolor":INK2,"xtick.color":MUT,"ytick.color":MUT,"axes.spines.top":False,"axes.spines.right":False})
df=pd.read_csv(f"{D}/streams_clean.csv",parse_dates=["date"]); daily=pd.read_csv(f"{D}/daily_summary.csv",parse_dates=["date"])
def head(fig,step,kind,title,sub):
    fig.text(0.04,0.955,f"{kind}  |  STEP {step}",fontsize=10,color=BLUE,weight="bold",va="top")
    fig.text(0.04,0.915,title,fontsize=19,weight="bold",va="top")
    fig.text(0.04,0.862,sub,fontsize=11,color=INK2,va="top")
def save(fig,name): fig.savefig(f"{O}/{name}",dpi=160,facecolor=SURF); plt.close(fig); print("saved",name)
def style(ax): ax.grid(axis="y",color=GRID,lw=.8); ax.set_axisbelow(True); ax.tick_params(length=0)

# 01 pipeline
fig=plt.figure(figsize=(13,5.2)); head(fig,1,"VALIDATION","From raw export to a dashboard ready dataset","Every stage has a check, and every check below was run on the real data")
steps=[("Raw export","9 music JSON files\nfrom Spotify"),("Combine","87,748 rows\ninto one table"),("Clean","rename fields, UTC to\nEastern, flag skips"),
 ("Validate","dupes, nulls, gaps,\nduration outliers"),("Aggregate","artist, daily, hour,\ntrack tables"),("Visualize","Tableau Public\ndashboard")]
ax=fig.add_axes([0,0,1,.78]);ax.axis("off");ax.set_xlim(0,13);ax.set_ylim(0,4)
for i,(t,s) in enumerate(steps):
    x=.35+i*2.14; ax.add_patch(FancyBboxPatch((x,1.1),1.75,1.9,boxstyle="round,pad=0.02,rounding_size=.12",fc="#cde2fb" if i!=3 else BLUE,ec="none"))
    ax.text(x+.875,2.6,t,ha="center",fontsize=12,weight="bold",color=INK if i!=3 else "white")
    ax.text(x+.875,1.85,s,ha="center",va="center",fontsize=9,color=INK2 if i!=3 else "white")
    ax.text(x+.875,.7,f"{i+1}",ha="center",fontsize=11,color=MUT)
    if i<5: ax.annotate("",xy=(x+2.1,2.05),xytext=(x+1.78,2.05),arrowprops=dict(arrowstyle="->",color=MUT,lw=1.5))
save(fig,"01_pipeline_overview.png")

# 02 integrity checks
chk=[("Files combined","9 of 9","pass"),("Total streams","87,748","info"),("Exact duplicate rows","0","pass"),("Missing values (nulls)","0","pass"),
 ("Zero millisecond streams",f"{(df.ms_played==0).sum():,}","review"),("Streams over 10 minutes",f"{(df.ms_played>600000).sum()}","review"),
 ("Longest single stream",f"{df.ms_played.max()/60000:.1f} min","review"),("Date range","Nov 6 2025 to Nov 6 2026","info")]
fig=plt.figure(figsize=(13,6)); head(fig,2,"VALIDATION","Integrity checks on the combined table","Pass means nothing to fix, review means a decision was made about how to treat it")
ax=fig.add_axes([.04,.03,.92,.75]);ax.axis("off");ax.set_xlim(0,10);ax.set_ylim(0,len(chk))
col={"pass":"#006300","review":"#b35c00","info":INK2}; lab={"pass":"PASS","review":"REVIEW","info":"INFO"}
for i,(a,b,s) in enumerate(chk):
    y=len(chk)-i-.5; ax.plot([0,10],[y-.5,y-.5],color=GRID,lw=.8)
    ax.text(.1,y,a,fontsize=13,va="center"); ax.text(6.3,y,b,fontsize=13,va="center",weight="bold",ha="right")
    ax.text(9.9,y,lab[s],fontsize=11,va="center",ha="right",color=col[s],weight="bold")
save(fig,"02_integrity_checks.png")

# 03 coverage calendar
full=pd.DataFrame({"date":pd.date_range(daily.date.min(),daily.date.max())}).merge(daily,on="date",how="left").fillna({"hours":0,"streams":0})
full["wk"]=((full.date-full.date.min()).dt.days+full.date.min().weekday())//7; full["dow"]=full.date.dt.weekday
fig=plt.figure(figsize=(14,4.8)); head(fig,3,"VALIDATION","Date coverage: where is the data missing?","Each square is one day, darker means more listening hours. Gray squares have zero streams")
ax=fig.add_axes([.06,.1,.9,.6]); W=full.wk.max()+1
for _,r in full.iterrows():
    c="#e1e0d9" if r.streams==0 else seq(min(r.hours/14,1)*.95+.05)
    ax.add_patch(plt.Rectangle((r.wk,6-r.dow),.88,.88,fc=c,ec="none"))
ax.set_xlim(0,W);ax.set_ylim(0,7);ax.set_yticks([i+.44 for i in range(7)]);ax.set_yticklabels(["Sun","Sat","Fri","Thu","Wed","Tue","Mon"],fontsize=8)
ms=full[full.date.dt.day<=7].groupby(full.date.dt.strftime("%b")).wk.min()
ax.set_xticks([v+.4 for v in ms.values]);ax.set_xticklabels(ms.index,fontsize=9);ax.spines[:].set_visible(False);ax.tick_params(length=0)
g=full[(full.date>="2025-12-04")&(full.date<="2026-01-04")];ax.annotate("32 day gap\nDec 4 to Jan 4",xy=(g.wk.mean()+.4,3.5),xytext=(g.wk.mean()+.4,7.7),ha="center",fontsize=10,color=INK,weight="bold",annotation_clip=False,arrowprops=dict(arrowstyle="-",color=MUT))
save(fig,"03_date_coverage_gap.png")

# 04 duration distribution
fig=plt.figure(figsize=(13,5.6)); head(fig,4,"VALIDATION","How long does each stream last?","Spotify counts a stream at 30 seconds, so anything shorter is flagged as a skip")
ax=fig.add_axes([.07,.12,.88,.62]);m=(df.ms_played/1000).clip(upper=300)
n,b,p=ax.hist(m,bins=np.arange(0,305,5),color=BLUE,edgecolor=SURF,lw=1)
for pt,l in zip(p,b[:-1]):
    if l>=30: pt.set_facecolor("#9ec5f4")
ax.axvline(30,color=INK,lw=1.4);ax.text(32,n.max()*.92,f"30 second line\n{(df.ms_played<30000).mean():.0%} of streams fall left of it (skips)",fontsize=10,va="top")
ax.set_xlabel("Seconds played (capped at 300 for display)");ax.set_ylabel("Streams");style(ax);ax.yaxis.set_major_formatter(lambda v,_:f"{v:,.0f}")
save(fig,"04_duration_distribution.png")

# 05 timezone check
fig=plt.figure(figsize=(13,5.4)); head(fig,5,"VALIDATION","Timezone check: UTC versus Eastern","Spotify exports UTC. Converting to Eastern moves the activity peak to match real waking hours")
ax=fig.add_axes([.07,.12,.88,.62]);utc=pd.to_datetime(df.end_time_utc if "end_time_utc" in df else df.end_time_local,utc=True).dt.hour.value_counts().sort_index().reindex(range(24),fill_value=0)
loc=df.hour.value_counts().sort_index().reindex(range(24),fill_value=0)
ax.plot(range(24),utc.values,color=MUT,lw=2,label="UTC (raw)");ax.plot(range(24),loc.values,color=BLUE,lw=2.4,label="Eastern (used)")
ax.set_xticks(range(0,24,2));ax.set_xlabel("Hour of day");ax.set_ylabel("Streams");ax.legend(frameon=False,loc="upper left");style(ax);ax.yaxis.set_major_formatter(lambda v,_:f"{v:,.0f}")
save(fig,"05_timezone_check.png")

# 06 heatmap
h=pd.read_csv(f"{D}/hour_weekday_heatmap.csv");pv=h.pivot(index="weekday_num",columns="hour",values="hours").reindex(range(7))
fig=plt.figure(figsize=(13,5.2)); head(fig,6,"VISUALIZATION","When do you listen? Weekday by hour","Darker means more hours. This is the heatmap you will build with Rows = Weekday, Columns = Hour")
ax=fig.add_axes([.08,.14,.82,.62]);im=ax.imshow(pv.values,cmap=seq,aspect="auto")
ax.set_yticks(range(7));ax.set_yticklabels(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]);ax.set_xticks(range(0,24,2));ax.set_xlabel("Hour of day (Eastern)");ax.tick_params(length=0)
for s in ax.spines.values(): s.set_visible(False)
cb=fig.colorbar(im,ax=ax,pad=.015,fraction=.03);cb.set_label("Hours listened");cb.outline.set_visible(False)
save(fig,"06_heatmap_weekday_hour.png")

# 07 skip rate by hour
sk=df.groupby("hour").is_skip.mean()*100
fig=plt.figure(figsize=(13,5.4)); head(fig,7,"VISUALIZATION","Skip rate by hour of day","Calculated field: SUM(is_skip) / COUNT(track). Daytime is for sampling, late night is for settling in")
ax=fig.add_axes([.07,.12,.88,.62]);ax.bar(sk.index,sk.values,color=BLUE,width=.72);ax.set_xticks(range(0,24,2));ax.set_ylabel("Skip rate (%)");ax.set_xlabel("Hour of day (Eastern)");style(ax)
ax.annotate(f"{sk.max():.0f}% peak",xy=(sk.idxmax(),sk.max()),xytext=(sk.idxmax(),sk.max()+6),ha="center",fontsize=10,weight="bold");ax.set_ylim(0,70)
save(fig,"07_skip_rate_by_hour.png")

# 08 monthly trend
mo=df.groupby("year_month").minutes_played.sum()/60;mo=mo.reindex(pd.period_range("2025-11","2026-11",freq="M").astype(str),fill_value=0)
fig=plt.figure(figsize=(13,5.4)); head(fig,8,"VISUALIZATION","Monthly listening hours with the data gap marked","Nov 2026 is a partial month (6 days). December reflects the missing data window, not low listening")
ax=fig.add_axes([.07,.14,.88,.6]);cols=[BLUE]*len(mo);cols[1]="#cde2fb";cols[-1]="#9ec5f4"
ax.bar(range(len(mo)),mo.values,color=cols,width=.7);ax.set_xticks(range(len(mo)));ax.set_xticklabels([pd.Period(x).strftime("%b\n%y") for x in mo.index],fontsize=9);ax.set_ylabel("Hours");style(ax)
ax.annotate("Data gap\n(Dec 4 to Jan 4)",xy=(1,mo.iloc[1]),xytext=(1,mo.max()*.55),ha="center",fontsize=10,weight="bold",arrowprops=dict(arrowstyle="-",color=MUT))
save(fig,"08_monthly_trend.png")

# 09 top artists
a=pd.read_csv(f"{D}/artist_summary.csv").head(10).iloc[::-1]
fig=plt.figure(figsize=(13,5.8)); head(fig,9,"VISUALIZATION","Top 10 artists by hours listened","Sort descending, Rows = Artist, Columns = SUM(hours). Add skip rate in the tooltip")
ax=fig.add_axes([.17,.1,.78,.64]);ax.barh(a.artist,a.hours,color=BLUE,height=.62)
for y,(hrs,sr) in enumerate(zip(a.hours,a.skip_rate)): ax.text(hrs+.8,y,f"{hrs:.0f} h  |  {sr:.0%} skipped",va="center",fontsize=9.5,color=INK2)
ax.set_xlim(0,a.hours.max()*1.3);ax.grid(axis="x",color=GRID,lw=.8);ax.set_axisbelow(True);ax.tick_params(length=0);ax.set_xlabel("Hours")
save(fig,"09_top_artists.png")

# 10 layout wireframe
fig=plt.figure(figsize=(13,7.4)); head(fig,10,"VISUALIZATION","Final dashboard layout","Arrange these four sheets on one Tableau dashboard, 1200 by 800 fixed size works well")
ax=fig.add_axes([.04,.03,.92,.76]);ax.axis("off");ax.set_xlim(0,12);ax.set_ylim(0,8)
def box(x,y,w,h,t,s,fc="#cde2fb"):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.02,rounding_size=.1",fc=fc,ec="none"));ax.text(x+w/2,y+h/2+.15,t,ha="center",va="center",fontsize=12,weight="bold");ax.text(x+w/2,y+h/2-.3,s,ha="center",va="center",fontsize=9,color=INK2)
for i,(t,v) in enumerate([("Hours","2,071"),("Streams","87,748"),("Artists","2,496"),("Skip rate","47%")]): box(.1+i*3,6.7,2.8,1.15,v,t,"#9ec5f4")
box(.1,3.3,5.9,3.2,"Monthly hours trend","gap annotated");box(6.1,3.3,5.8,3.2,"Weekday by hour heatmap","colored by hours")
box(.1,.1,5.9,3.0,"Top 10 artists","hours, skip rate in tooltip");box(6.1,.1,5.8,3.0,"Skip rate by hour","the discovery story")
save(fig,"10_dashboard_layout.png")
