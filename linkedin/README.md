# LinkedIn post kit: Spotify listening dashboard

Everything needed to post about this project. Prepared 2026-11-10.

Every number below comes from this repository's main `README.md`. If you change the dashboard or the data,
update the numbers here before posting.

## 1. Before you post

These are in priority order. The first three are worth doing; the rest are optional polish.

- [ ] **Open the live dashboard link in a private browser window** and confirm it loads without being signed in.
- [ ] **Decide where the Career Companion code lives.** It currently sits in a draft pull request on this
      repository, which anyone following the GitHub link can see. Moving it to its own repository keeps this
      one about the Spotify project.
- [ ] **Fix the `tableau` folder mismatch.** The main README says the repository contains an exported workbook
      in a `tableau` folder. That folder is not in the repository. Either add the `.twbx` file or remove the row.
- [ ] Tidy the Overview page (seen in `images/12_dashboard_overview_page.png`; the live page may already differ):
  - The line "Showing: all listening (click an artist)" is cut off at the bottom.
  - Faint leftover headings "KPIs" and "Showing" are visible.
  - The top right of the page is empty.
  - One axis reads "Month of Month Start".
- [ ] Rename the workbook on Tableau Public. The address still contains the defaults `Book1` and `Dashboard1`.
      If you rename it, update the link in the main README and in section 6 below.
- [ ] The Habits page (`images/11_dashboard_habits_page.png`) has large empty areas and leftover labels
      ("Value", "Measure Names", "Filters"). It is not used in this post. Fix it before featuring it anywhere.

## 2. The post

Two versions. Use one. Both are written to match the plain, first-person voice of the project README.

### Main version (about 190 words)

```
I skipped 47% of the songs I played this past year.

At 5 AM it was 9%. At 3 PM it was 58%.

I requested my listening history from Spotify and built a Tableau dashboard around one question: when do I explore, and when do I settle in?

What the data showed:
• 87,748 streams, 2,071 hours and 2,496 artists over one year
• Overnight, about 26% of streams get skipped. Between 10 AM and 6 PM it is near 55%.
• 835 of those artists appear exactly once

My read: late nights are for music I already know, and daytime is for sampling. The data shows the pattern, not the reason.

Most of the work came before the charts. I combined 9 export files in Python and pandas, checked for duplicates and nulls (none), and converted timestamps from UTC to Eastern so the hours were right. I also found 32 days with no data at all. I marked that gap on the chart and did not fill it in, because the data was missing, not low.

The dashboard is live on Tableau Public and the full process is on GitHub. Links are in the comments.

#DataAnalytics #Tableau #Python
```

### Short version (about 80 words)

```
I skipped 47% of the songs I played this past year. At 5 AM it was 9%. At 3 PM it was 58%.

I built a Tableau dashboard from my own Spotify history (87,748 streams, 2,071 hours) to ask when I explore and when I settle in. Late nights look like familiar music. Daytime looks like sampling.

Cleaned and validated in Python and pandas, including a 32 day gap I marked and did not fill in.

Live dashboard and process write-up in the comments.

#DataAnalytics #Tableau #Python
```

### First comment (post it yourself right after publishing)

```
Live dashboard: https://public.tableau.com/views/Book1_17941744917780/Dashboard1
Process and code: https://github.com/Danorete/spotify-listening-bi
```

If you would rather put the links in the post itself, replace the "Links are in the comments" sentence with
the two lines above. Whether links in the post body affect how widely it is shown is a common belief that I
have not been able to verify.

## 3. Images

Three upload-ready files are in `linkedin/images/`. Upload them in this order.

| Order | File | Size | What it shows | Why it is here |
|---|---|---|---|---|
| 1 | `1_dashboard_overview.png` | 2420 x 1959 | The finished Overview page | The result. It carries the headline numbers and the main chart. |
| 2 | `2_skip_rate_by_hour.png` | 2080 x 1387 | Skip rate for each hour of the day | The finding, on its own and easy to read. |
| 3 | `3_integrity_checks.png` | 2080 x 1387 | The data checks: files, duplicates, nulls, date range | Shows the validation work, which is what analyst roles screen for. |

Images 2 and 3 are copies of `images/07_skip_rate_by_hour.png` and `images/02_integrity_checks.png` with
blank space added above and below. The originals are about 2.4 times wider than tall, and the padding keeps
their edges from being cut off when several images are shown together. Nothing in the charts was changed.

Check the preview before you publish. If an image looks cropped, post image 1 alone.

### Alt text (paste into LinkedIn's alt text box for each image)

1. `Dark dashboard titled "What my skips say about how I listen". Headline numbers: 325 active days, 87,748 streams, 2,071 hours, 47% skip rate. Four charts: listening hours by month with a marked data gap, a weekday by hour heatmap, skip rate by hour of day peaking at 58%, and the top 10 artists.`
2. `Bar chart of skip rate by hour of day in Eastern time. The rate is lowest at 5 AM, about 9%, and highest at 3 PM, 58%. Daytime hours from 10 AM to 6 PM are all near or above 50%.`
3. `Table of integrity checks on the combined data. Files combined: 9 of 9, pass. Total streams: 87,748. Exact duplicate rows: 0, pass. Missing values: 0, pass. Three items marked for review, including 493 zero millisecond streams. Date range: Nov 6 2025 to Nov 6 2026.`

### Images not to use yet

- `11_dashboard_habits_page.png`: unfinished layout (see section 1). It also shows artist photos, which are
  other people's images.
- `03_date_coverage_gap.png`: nearly three times wider than tall, so it will display very small.

## 4. Video (optional)

The images are enough for a first post. A short screen recording adds one thing the images cannot show: the
dashboard is interactive. Only record it after the Overview page is tidied.

**What to record (30 to 45 seconds, no narration needed):**

| Seconds | Show |
|---|---|
| 0 to 5 | The Overview page, still. Let the title and headline numbers be read. |
| 5 to 15 | Move the pointer slowly across the skip rate chart, from the 5 AM bar to the 3 PM bar. |
| 15 to 25 | Hover over the data gap note on the monthly chart. |
| 25 to 35 | Click one artist to filter the page, pause, then clear the filter. |
| 35 to 45 | Click the Habits button only if that page has been tidied. Otherwise stop at 35. |

**How to record on a Mac:**

1. Open the live dashboard in a browser window and make the window roughly 16:9.
2. Press Shift + Command + 5, choose "Record Selected Portion", and drag the frame around the dashboard only.
3. Click Record. Stop from the menu bar when finished. The file saves as `.mov`.
4. Trim the start and end in QuickTime Player (Edit, then Trim).

**Things to decide:**

- Clicking an artist shows the artist photo row. Those photos are other people's images. Either skip that
  step or accept that they appear.
- Many people watch with sound off. If you add narration, add on-screen text or captions as well.
- If you post the video, use it in place of the images. A LinkedIn post takes images or a video, not both
  (my understanding; check when composing).

**LinkedIn's video limits** (from LinkedIn Help, checked 2026-11-10):

| Limit | Value |
|---|---|
| Length | up to 15 minutes |
| File size | 75 KB to 5 GB |
| Shape | between 1:2.4 and 2.4:1 |
| Frame rate | 10 to 60 frames per second |

A QuickTime `.mov` recording normally uploads as is. If LinkedIn rejects it, export it as MP4 first. I did
not confirm the full list of accepted file types.

## 5. Fact sheet

Use these exact figures. Each one is in the main README.

| Fact | Figure |
|---|---|
| Period covered | November 6, 2025 to November 6, 2026 |
| Streams | 87,748 |
| Hours listened | 2,071 |
| Distinct artists | 2,496 |
| Artists played exactly once | 835 |
| Streams skipped (played under 30 seconds) | 47% |
| Skip rate, midnight to 5 AM | about 26% |
| Skip rate at 5 AM | 9% |
| Skip rate, 10 AM to 6 PM | near 55% |
| Peak skip rate, around 3 PM | 58% |
| Average listening per active day | 6.4 hours |
| Export files combined | 9 of 9 |
| Duplicates and nulls found | 0 and 0 |
| Gap in the data | 32 days, December 4, 2025 to January 4, 2026 |
| Timezone handling | Spotify exports UTC; converted to Eastern |
| Tools | Python, pandas, matplotlib, Tableau Public |

Two figures appear on the dashboard but not in the main README: 325 active days, and the individual review
items in the integrity table (493 zero millisecond streams, 66 streams over 10 minutes, longest stream
25.7 minutes). They are fine to mention because the images show them.

## 6. Links

- Live dashboard: https://public.tableau.com/views/Book1_17941744917780/Dashboard1
- Repository: https://github.com/Danorete/spotify-listening-bi

## 7. Questions people may ask

The answers below are already in the main README. Reread them before posting so your replies are quick.

| Question | Where the answer is |
|---|---|
| Why does under 30 seconds count as a skip? | It is Spotify's own definition of a stream. Shorter plays are flagged and kept in the data. |
| Why not fill in the December gap? | The data is missing, not low. The gap is marked on the trend chart. |
| Why convert the timezone? | Spotify exports UTC. Without converting to Eastern, every hour-of-day pattern would be shifted. |
| What is "Unknown Artist"? | 931 streams, 93% skipped. Excluded from artist rankings because it is not a real artist. |
| Does a high skip rate mean you dislike an artist? | No. Among artists with at least 300 streams, skip rates run from about 25% to 64%. Playing an artist often does not mean finishing their tracks. |
| What does the pattern mean? | The data shows the pattern and not the reason. Late night looks settled; daytime looks like sampling. |

Two questions the README does not answer. Have your own answer ready:

- What would you do next with this data?
- What did you learn that you would apply at work?

## 8. After you post

- Add the post's link to the "Spotify listening dashboard" entry in Career Companion's Evidence, as proof.
- Reply to comments within the first day.
- When a recruiter or analyst reaches out because of it, add them under People & roles and record the outcome.

## What was and was not checked

- Checked: every figure in the post against the main README; the three images open and are not cropped;
  LinkedIn's video limits, from LinkedIn Help on 2026-11-10.
- Not checked: the live Tableau page (the notes in section 1 come from the screenshots in `images/`); how
  LinkedIn crops multiple images; whether links in the post body affect reach; accepted video file types.
