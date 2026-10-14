# Put it on your phone (one-time, about 10 minutes on the MacBook)

The engine runs on GitHub's servers three times a day and publishes the dashboard as a web app you add to your home screen. After this setup you never need the MacBook again; starters and manual re-runs can be done from the GitHub app on your phone.

## 1. Create the repository

1. Sign in to github.com, click **New repository**, name it `nhl-early-goal`, keep it **Private**, do not add a README, click **Create repository**.
2. On the MacBook, in Terminal:

```bash
cd nhl-early-goal
git init -b main
git add .
git commit -m "early goal desk"
git remote add origin https://github.com/<your-username>/nhl-early-goal.git
git push -u origin main
```

(If git asks you to log in, use a personal access token from GitHub Settings → Developer settings → Tokens, or install the GitHub CLI and run `gh auth login`.)

## 2. Turn on GitHub Pages

Repository → **Settings** → **Pages** → under *Build and deployment* choose **Deploy from a branch**, branch **main**, folder **/docs**, Save.

Your site address will be `https://<your-username>.github.io/nhl-early-goal/`. For a private repository, Pages needs GitHub Pro (a few dollars a month) or the repository can be made public; the data in it is public NHL play-by-play and your overrides, nothing else.

## 3. Run it once

Repository → **Actions** → **Update slate** → **Run workflow**. The first run takes about 3 minutes (it downloads three seasons of play-by-play). When it finishes, open the site address on your phone.

## 4. Add to Home Screen

iPhone: open the site in Safari → Share → **Add to Home Screen**. Android: Chrome → menu → **Add to Home screen**. The icon opens full screen and shows the latest published slate; the slate selector at the top shows past days.

## Daily use

* The workflow runs at about 10am, 3pm and 6:35pm Eastern. Open the app after 6:35pm for the most complete starting-goalie picture.
* To enter confirmed starters yourself: GitHub app → repository → `data/overrides.json` → edit → commit, then Actions → Update slate → Run workflow. The site refreshes within a few minutes.
* To re-run at any time: Actions → Update slate → Run workflow.
* Your book prices typed into the price-check box stay in your phone's browser; they are not sent anywhere.

## If the DailyFaceoff scrape stops working

The dashboard chip "goalies" tells you where the starters came from. If it says "usage heuristic for the rest" for most teams, the scrape returned nothing that run; overrides.json is the fallback. The scrape is best effort because that site changes its layout.

## Costs

GitHub Actions gives private repositories 2,000 free minutes a month; three runs a day at about 2 minutes each uses roughly 180. Public repositories are free without limit.
