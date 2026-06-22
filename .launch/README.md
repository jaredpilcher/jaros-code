# .launch — Your two-week launch playbook

This folder is your hand-held, copy-paste launch kit. You are new to public dev
channels, so this is written to be followed literally. Do the steps in order. Paste
the content as-is (after filling the few bracketed blanks). Iterate only if you must.

**Your goal (stated):** influence, and securing your place in agentic engineering.
Not money, not retirement. Every choice below serves *that* goal.

**The one strategic idea behind this whole plan:** you are not launching a tool. You
are introducing a *point of view* about how agentic engineering is going to work, and
using your code as the proof. Tools get a few likes. A thinker-with-evidence gets
cited and remembered. So every post leads with an idea, and Jaros/jaros-code appear as
*evidence*, never as the headline.

---

## THE GOLDEN RULES (read once, never break)

1. **Never claim a number you have not measured and cannot reproduce.** This is the
   fastest way to lose credibility with the exact people you want to impress. The
   commit-replay/"how far does a tiny model get on real repos" number is NOT in any
   post here, because you have not run that eval yet. When you have run it honestly,
   it becomes your most powerful Week-3 post. Until then: thesis + mechanism + honest
   small signal only.
2. **Lead with the failure, not just the win.** The field is drowning in over-claimed
   demos. Your differentiator is honesty — showing where the harness *stops* and the
   model ceiling begins (the "listops" story). That honesty is what makes people trust
   your *other* numbers. Do not sand it off.
3. **Be transparent that an agent did most of the engineering, under your direction.**
   This is an asset, not a confession. An AI agent doing sustained, supervised,
   autonomous engineering on a real codebase IS the thing the field is obsessed with.
   Foreground it. Your role is architect/director, and that's a legitimate, valuable
   role — own it plainly.
4. **One canonical home, then syndicate.** Publish the long-form on your blog (owned
   audience), then repost adapted versions to LinkedIn and X with a link back. Don't
   let your best thinking die inside a LinkedIn-native post.
5. **Engage 20 minutes a day, every posting day.** Reply to every thoughtful comment.
   Comment on 3 other people's posts in the space. Influence is a conversation, not a
   broadcast.

---

## FILL-IN LEGEND (replace these everywhere before posting)

- `[BLOG_URL]` — the live URL of the published blog post you're linking to.
- `[REPO_URL]` — `https://github.com/jaredpilcher/jaros` once it's public.
- `[X_HANDLE]` — your X/Twitter @handle.
- `[BLOG_HOME]` — your blog's base URL (e.g. your Substack).

If a blank isn't listed here, the content is ready to paste verbatim.

---

## ACCOUNTS YOU NEED (set up Day 1, ~45 minutes total)

You probably have LinkedIn. You need three more homes:

1. **A blog with an owned email list — recommended: Substack** (free, fastest for a
   newcomer, gives you subscribers you own). Alternative: dev.to (more builder-native,
   better SEO) — but Substack's email list is the better long-term asset for *your*
   goal. Pick Substack unless you already prefer another. Name it after your point of
   view, not the tool — e.g. "Agentic Engineering Notes" or just your own name.
2. **X / Twitter** — this is where the agentic-engineering in-crowd actually argues and
   decides who's serious. Set your bio (copy in `syndication.md`). If you have a dormant
   account, reuse it.
3. **Reddit** — you just need an account with a little karma. `r/LocalLLaMA` is the
   single best-fit audience on the internet for "tiny local model + clever harness."
   They will genuinely care. (Lurk/comment a couple times before Week 2 so you're not a
   zero-karma account when you post.)

You do NOT need: a website, a logo, a newsletter design, a Discord. Resist polishing.
Shipping the *ideas* is the work.

---

## THE SCHEDULE

Dates assume you start the week of **Mon Jun 22, 2026**. Shift if you start later;
keep the *shape*. ~30–60 min/day. The engineering (commit-replay eval) runs in the
background — that's a separate track noted at the bottom.

### WEEK 1 — Establish the voice (no code release; just writing)

| Day | Do this | Content file |
|-----|---------|--------------|
| **Mon Jun 22** | Set up Substack + X + Reddit accounts. Paste your X bio and LinkedIn headline. Don't post yet. | `syndication.md` → "Profiles" |
| **Tue Jun 23** | **Publish Post 1** ("The Genius and the Jig") on your blog. Then *same day, within an hour*: post the LinkedIn version and the X thread, both linking to `[BLOG_URL]`. Best times: LinkedIn 8–10am your time; X 9am–12pm ET. | `post-1-the-genius-and-the-jig.md`, `syndication.md` |
| **Wed Jun 24** | 20-min engagement: reply to every comment on Post 1. Comment thoughtfully on 3 other agentic-eng posts. | — |
| **Thu Jun 25** | 20-min engagement again. Quietly kick off your commit-replay eval (engineering track). | — |
| **Fri Jun 26** | Post the Week-1 "build in public" micro-post on X + LinkedIn (the honest listops teaser — seeds Post 2). | `syndication.md` → "Micro-posts" |

### WEEK 2 — The mechanism + the Jaros substrate drop

| Day | Do this | Content file |
|-----|---------|--------------|
| **Mon Jun 29** | **Publish Post 2** ("Why Small Models Fail at Agentic Coding"). Syndicate to LinkedIn + X same day. | `post-2-why-small-models-fail.md`, `syndication.md` |
| **Tue Jun 30** | Prep the Jaros repo for public: add the README intro, add `LICENSE` (Apache-2.0), make sure it's clean. Do NOT release yet. | `jaros-release-kit.md` |
| **Wed Jul 1** | Final repo polish + dry-run the install yourself from a clean clone. Write nothing public. | `jaros-release-kit.md` |
| **Thu Jul 2** | **Release Jaros.** Flip the repo public. Then in order: (1) `r/LocalLLaMA` post ~9am ET, (2) X announce thread, (3) LinkedIn announce, (4) optional Show HN ~8–9am ET. Frame it as the *substrate*; tease jaros-code as the payoff. | `jaros-release-kit.md` |
| **Fri Jul 3** | Heavy engagement day — release days generate the most comments; reply to all. Note what resonated for Week-3 planning. | — |

### After (Week 3+, not scripted here)
- When your commit-replay eval has an honest number → that's your flagship Post 3:
  *"How far does a free, tiny, local model actually get on real repo histories?"*
  This is the post that can define you in the space. Don't rush it; ship it true.
- Then the jaros-code launch, with that finding as the anchor.

---

## ENGINEERING TRACK (parallel, your job, not blocking the posts)
- This week: run the commit-replay evaluation on a few important repos (test-gated,
  filtered to commits that have a checkable oracle — see our chat notes). The number it
  produces is Week-3 content. The posts in this kit deliberately do not depend on it.

---

## IF YOU ONLY DO ONE THING
Publish Post 1 on Tuesday and reply to every comment. That single act — a thesis-led
post under your name, defended in the replies — moves you from "person with a tool" to
"person with a point of view" more than anything else in this folder.
