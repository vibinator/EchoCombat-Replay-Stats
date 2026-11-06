# Achievement tiers — proposal (for approval, nothing implemented yet)

Written 2026-10-31 against Beta 44. Ladder: **bronze, silver, gold, platinum, diamond** (as on Clean Sweep / Special
Delivery; user chose to keep diamond). Once approved this ships as the beta after the medal-colour update, Beta 46 (version bump + Changelog entry).

## What I checked
- All 108 rules in `app/backend/achievements.py`; only 2 (Clean Sweep, Special Delivery) are tiered today. The other 106
  are one-shot with white / bronze / silver / gold meaning 25 / 50 / 75 / 100 % of the way, so "bronze" today means
  "halfway", not "an easier version of the challenge".
- The archive: 8,090 players, **1,780 with 10+ games** (the base for every percentage below), 206,262 appearances.
  Targets were chosen from the real distributions, not guessed. Scripts used are throw-away (scratchpad), the numbers
  are in the tables.

## Problems found in the current rules
1. **Several targets are far out of reach.** Share of players (10+ games) who complete them today:
   Super Ultra Hyper Turbo (35 m/s) 0.1 %, Combat pubs per day (35) 0.5 %, all 64 loadouts 0.4 %, Combat pubs per week
   (100) 0.8 %, Capture Point / Payload 50 games in a week 1.0 %, Unstoppable (10 wins in a row) 2.3 %. Tiers fix this:
   the hard target stays as the top medal and the steps below it are reachable.
2. **Several are trivial.** "Near an enemy 2 %" is met by 100 % of players (median 24 % of a game, 14 % of a week, 11 %
   all-time); "near a teammate 22 % in a week" by 56 %, "13 % all-time" by 70 %. They give no spread at all.
3. **The 25 % "white" step is not a real medal** (a lock-coloured frame), and it makes progress bars look half-done for
   everyone. Ladders replace it.
4. **Overall % is dominated by 100+ near-identical gear rules** (12 daily + 12 weekly + 12 veteran + ...), so it says more
   about which gear you like than how well you play. Medals give a better headline number (see "Medal Collector").
5. Estimated rules (deaths, payload push / block) rely on estimated data; their ladders are kept low and stay marked
   "estimated".

## Design rules for the ladders
- **Gold = today's target** where that target is reachable by roughly 3-15 % of players; otherwise the old target moves to
  where its rarity belongs (e.g. Combat pubs all time 550 is platinum, weekly Capture Point 50 is diamond).
- Aim per rule: bronze ≈ 25-60 % of active players, silver ≈ 10-30 %, gold ≈ 2-15 %, platinum ≈ 1-5 %, diamond ≈ 0.1-1 %.
- Progress = 20 % per medal (existing behaviour), the description lists every target (existing behaviour), the badge
  shows "12 / 25 for platinum".
- **Period rules stay "best period"**: a day rule counts your best calendar day, a week rule your best week, a per-game
  rule your best single game. Needs a small engine change (today tiering only supports all-time counts), see below.
- Rules that are a yes / no event stay single-step (no ladder makes sense): Jack of All Trades, Ordnance Sampler, Tac Mod
  Tinkerer, Beam Me Up, Arsenal Overload, Ordnance Overload, Forbidden Arsenal (87-89, 86, 109-111).

## Proposed ladders — existing rules converted
"Reaching" = share of the 1,780 players with 10+ games who would hold that medal (bronze / silver / gold / platinum /
diamond). All-time average rows use the 430 players with 50+ games, as the rules already require.

### Gear
| Rule family | ids | Targets | Today's target (share completing) | Share reaching each |
|---|---|---|---|---|
| Use only one item in one day (12 rules) | 5-16 | 5 / 10 / 15 / 22 / 30 games | 15 (Pulsar 1.9 %, Comet 1.2 %) | Pulsar 35.4 / 11.4 / 1.9 / 0.7 / 0.3 %; Comet 10.6 / 4.6 / 1.2 / 0.3 / 0.0 % (see note) |
| Use only one item in one week (12 rules) | 30-41 | 5 / 10 / 20 / 40 / 75 games | 20 (Pulsar 4.9 %, Meteor 1.8 %) | Pulsar 38.2 / 15.7 / 4.9 / 1.1 / 0.3 %; Meteor 7.9 / 3.2 / 1.8 / 0.7 / 0.1 % |
| Gear veterans: games using it (12 rules) | 55-66 | 10 / 30 / 100 / 300 / 1000 games | 100 (Pulsar 7.1 %, Stun Field 1.9 %) | Pulsar 69.3 / 24.5 / 7.1 / 2.3 / 0.7 %; Stun Field 27.2 / 7.4 / 1.9 / 0.8 / 0.2 % |
| Gearhead: games in a row on one loadout, in a week | 42 | 5 / 10 / 25 / 50 / 100 | 25 (1.6 %) | 22.2 / 7.5 / 1.6 / 0.2 / 0.0 % |
| Different loadouts used, 3+ min each (of 64) | 67 | 8 / 16 / 32 / 48 / 64 | 64 (0.4 %) | 41.7 / 14.0 / 3.8 / 0.9 / 0.4 % |
| Days using all 12 equipables (replaces "in one day") | 17 | 1 / 3 / 10 / 25 / 50 days | 1 day (10.1 %) | 10.1 / 1.5 / 0.4 / 0.1 / 0.1 % |
| Unreleased gear: Starburst / Protostar / Quark / Translocator games | 80-82, 84 | 1 / 5 / 25 / 100 (50) / 300 (100) | 25 (0.5-1.1 %) | Starburst 12.4 / 4.2 / 1.1 / 0.1 / 0.1 %; Quark (1/5/25/50/100) 13.1 / 4.2 / 0.5 / 0.3 / 0.1 % |
| Blazar games | 83 | 1 / 2 / 5 / 10 / 15 | 5 (1.0 %) | 5.6 / 2.9 / 1.0 / 0.2 / 0.1 % |
| The four "now public" gear veterans | 105-108 | same as the gear veterans | 100 | (data too young, retune after launch) |
| "Use only" Starburst / Protostar / Quark / Translocator in a day | 101-104 | 2 / 5 / 10 / 15 / 20 games | 10 | (data too young, retune after launch) |

*Note on the daily gear ladder:* diamond (30 games of one item in a day) is about one player per item; that is intended.

### Maps and modes
| Rule family | ids | Targets | Today's target (share completing) | Share reaching each |
|---|---|---|---|---|
| One map in a day (4 maps) | 25-28 | 2 / 3 / 4 / 6 / 10 games | 4 (24.7 %) | 77.2 / 43.7 / 24.7 / 8.8 / 1.5 % |
| One map in a week | 50-53 | 4 / 6 / 8 / 16 / 30 | 8 (15.5 %) | 45.8 / 24.4 / 15.5 / 3.6 / 0.7 % |
| One map all time | 75-78 | 5 / 15 / 40 / 150 / 500 | 40 (9.3 %) | 64.6 / 22.7 / 9.3 / 3.2 / 1.0 % |
| Capture Point games in a day | 19 | 4 / 6 / 8 / 12 / 20 | 8 (13.4 %) | 56.2 / 28.1 / 13.4 / 4.0 / 0.2 % |
| Payload games in a day | 20 | 4 / 6 / 8 / 12 / 20 | 8 (14.2 %) | 57.8 / 27.4 / 14.2 / 4.2 / 0.4 % |
| Capture Point games in a week | 44 | 10 / 18 / 25 / 40 / 50 | 50 (1.0 %) | 25.9 / 10.6 / 5.2 / 1.7 / 1.0 % |
| Payload games in a week | 45 | 10 / 18 / 25 / 40 / 50 | 50 (1.0 %) | 25.0 / 9.9 / 5.3 / 1.3 / 1.0 % |
| Capture Point games all time | 69 | 10 / 25 / 50 / 250 / 1000 | 50 (13.5 %) | 58.9 / 25.5 / 13.5 / 3.5 / 1.0 % |
| Payload games all time | 70 | 10 / 25 / 50 / 250 / 1000 | 50 (13.0 %) | 56.9 / 24.3 / 13.0 / 3.4 / 1.0 % |
| Combat pubs in a day | 29 | 10 / 15 / 20 / 30 / 40 | 35 (0.5 %) | 29.0 / 11.2 / 4.9 / 1.4 / 0.2 % |
| Combat pubs in a week | 54 | 15 / 30 / 60 / 100 / 150 | 100 (0.8 %) | 34.7 / 12.2 / 3.2 / 0.8 / 0.1 % |
| Combat pubs all time | 79 | 25 / 100 / 250 / 550 / 2000 | 550 (3.2 %) | 46.5 / 13.5 / 6.4 / 3.2 / 1.0 % |

### Skill and movement (single game, week, all-time average)
Per-game percentages use games of 3+ minutes (existing rule). Weekly / all-time averages keep their existing minimums.
| Rule family | ids | Targets | Today's target (share completing) | Share reaching each |
|---|---|---|---|---|
| Top speed in one game | 23 | 16 / 20 / 24 / 28 / 35 m/s | 35 (0.1 %) | 50.7 / 14.6 / 4.4 / 0.8 / 0.1 % |
| Near a teammate, one game | 21 | 40 / 50 / 60 / 75 / 90 % | 50 (42.6 %) | 65.0 / 42.6 / 23.7 / 8.0 / 3.5 % |
| Near an enemy, one game | 22 | 2 / 15 / 30 / 50 / 75 % | 2 (100 %) | 100 / 88.1 / 31.1 / 9.6 / 3.9 % |
| Inverted, one game | 24 | 10 / 25 / 50 / 75 / 90 % | 50 (17.1 %) | 54.5 / 36.0 / 17.1 / 8.7 / 5.2 % |
| Games with 3 or fewer deaths (counts games, not one) | 18 | 1 / 5 / 15 / 50 / 250 | 1 (80.2 %) | 80.2 / 25.1 / 9.0 / 3.3 / 0.6 % |
| Weekly average speed | 48 | 3.5 / 4 / 4.5 / 5 / 6 m/s | 4.5 (2.6 %) | 23.1 / 7.7 / 2.6 / 1.5 / 0.9 % |
| Weekly near a teammate | 46 | 25 / 30 / 35 / 45 / 60 % | 22 (56.4 %) | 43.9 / 28.5 / 18.6 / 7.8 / 2.2 % |
| Weekly near an enemy | 47 | 10 / 15 / 20 / 30 / 50 % | 2 (100 %) | 83.3 / 46.4 / 18.9 / 5.3 / 1.6 % |
| Weekly inverted | 49 | 5 / 10 / 15 / 30 / 50 % | 15 (22.6 %) | 45.3 / 31.4 / 22.6 / 10.2 / 4.2 % |
| All-time average speed (50+ games) | 73 | 2.9 / 3.1 / 3.3 / 3.5 / 3.7 m/s | 3.5 (1.4 %) | 35.1 / 15.6 / 5.1 / 1.4 / 0.7 % |
| All-time near a teammate (50+) | 71 | 14 / 16 / 19 / 22 / 25 % | 13 (70.2 %) | 60.9 / 45.3 / 17.9 / 4.7 / 1.2 % |
| All-time near an enemy (50+) | 72 | 6 / 9 / 12 / 14 / 15.5 % | 2 (100 %) | 98.8 / 80.5 / 30.5 / 9.1 / 1.6 % |
| All-time inverted (50+) | 74 | 2 / 4 / 8 / 30 / 60 % | 4 (35.6 %) | 50.9 / 35.6 / 18.4 / 4.7 / 1.4 % |
| Deaths all time (Pixel Party) | 68 | 100 / 500 / 1000 / 5000 / 20000 | 1000 (10.7 %) | 76.9 / 18.8 / 10.7 / 3.0 / 0.6 % |
| Pew Pew Proof (average < 5 deaths over 25+ games in a week) | 43 | **needs your call**, see questions | | the best week average in the archive is 2.5 deaths; I did not get a clean distribution, so I propose leaving it single-step for now |

### Wins and payload
| Rule family | ids | Targets | Today's target (share completing) | Share reaching each |
|---|---|---|---|---|
| Wins all time (Centurion) | 92 | 10 / 25 / 100 / 500 / 2000 | 100 (4.7 %) | 29.3 / 12.6 / 4.7 / 1.2 / 0.1 % |
| Win streak (merges On a Roll + Unstoppable) | 90, 91 | 3 / 5 / 8 / 12 / 16 | 5 and 10 (2.3 % for 10) | 46.0 / 19.7 / 5.4 / 1.2 / 0.3 % |
| Hold the Line (win Payload defending) — count of wins | 95 | 1 / 5 / 15 / 50 / 200 | 1 (57.7 %) | 57.7 / 19.8 / 7.6 / 2.8 / 0.9 % |
| Clean Sweep, Special Delivery (already tiered) | 93, 94 | unchanged 1 / 5 / 10 / 25 / 50 | | 62.4 / 22.5 / 11.2 / 5.4 / 3.3 % (Clean Sweep). Diamond is easy for a game this common; optional: raise to 100 |
| Pedal to the Metal: best push in one game | 96 | 1 / 2 / 3 / 4 / 6 min | 3 (19.4 %) | 57.2 / 41.6 / 19.4 / 4.8 / 0.3 % |
| Immovable Object: best block in one game | 97 | 30 s / 1 / 1.5 / 2 / 3 min | 1 min (15.6 %) | 36.4 / 15.6 / 5.7 / 2.0 / 0.3 % |
| Freight Train: push time in total | 98 | 10 min / 30 min / 1 h / 5 h / 15 h | 5 h (1.3 %) | 21.5 / 8.3 / 4.7 / 1.3 / 0.1 % |
| Showboat: emotes in one game | 99 | 3 / 6 / 10 / 15 / 25 | 10 (7.9 %) | 46.4 / 21.0 / 7.9 / 2.6 / 0.5 % |
| Dance Floor Legend: emotes in total | 100 | 10 / 50 / 200 / 500 / 2000 | 500 (2.4 %) | 43.5 / 16.2 / 5.5 / 2.4 / 0.3 % |
| Overclocked (Overcharge games) | 112 | 1 / 3 / 5 / 10 / 25 | 5 | no player has more than 2 games, retune after launch |

## Proposed new challenges (all ladders, all from data already stored)
Same base and format as above.
| Challenge (working name) | What it counts | Targets | Share reaching each |
|---|---|---|---|
| Frequent Flyer | Games played | 10 / 50 / 200 / 1000 / 5000 | 100 / 24.2 / 7.6 / 2.4 / 0.1 % |
| Regular | Days played | 5 / 15 / 40 / 100 / 300 | 79.8 / 27.9 / 9.3 / 3.7 / 1.1 % |
| Loyal Bot | Different weeks played | 3 / 8 / 20 / 50 / 100 | 82.8 / 34.1 / 9.9 / 3.3 / 0.8 % |
| Daily Grind | Longest run of consecutive days played | 3 / 5 / 7 / 14 / 30 | 53.7 / 18.2 / 8.7 / 2.4 / 0.7 % |
| Time Well Wasted | Hours played | 1 / 5 / 20 / 100 / 500 | 98.5 / 30.9 / 9.4 / 2.9 / 0.4 % |
| Overtime | Games of 10+ minutes | 5 / 20 / 50 / 250 / 1000 | 50.6 / 14.4 / 7.4 / 2.3 / 0.4 % |
| Hot Day | Wins in one day | 3 / 5 / 8 / 12 / 20 | 44.5 / 21.6 / 7.7 / 2.2 / 0.3 % |
| Point Taker | Capture Point wins | 3 / 10 / 30 / 100 / 400 | 49.8 / 17.4 / 6.5 / 2.8 / 0.9 % |
| Cargo Hauler | Payload wins | 3 / 10 / 30 / 100 / 400 | 43.9 / 15.1 / 6.1 / 2.4 / 0.7 % |
| Grand Tour | Wins on each of the 4 maps (the lowest of the four counts) | 1 / 5 / 15 / 50 / 150 | 38.1 / 11.2 / 5.3 / 2.2 / 1.0 % |
| Weapons Master | Games with the least-used of the 4 weapons | 1 / 5 / 15 / 50 / 150 | 77.9 / 32.1 / 10.2 / 3.6 / 0.9 % |
| Loadout Scholar | Games with the least-used of the 12 equipables | 1 / 5 / 15 / 50 / 100 | 42.1 / 10.5 / 3.4 / 1.0 / 0.6 % |
| Immovable Object | Payload block time in total | 2 / 10 / 30 / 60 / 120 min | 22.4 / 4.8 / 1.5 / 0.7 / 0.1 % |
| Winning Habit *(optional)* | Win rate with 50+ games | 40 / 45 / 50 / 55 / 60 % | 16.0 / 11.3 / 7.6 / 3.9 / 1.9 % (win rate depends on teammates and on who plays together; I would skip it) |
| **Medal Collector** (meta) | Gold-or-better medals held across all other challenges | to be set after the ladders exist (needs the final list to size) | n/a yet |

## What has to change in the code (for Beta 46)
- `achievements.py`: extend the tiered mechanism (`levels`, `count`, `_levelled`) so a count can be "best day / best week /
  best game / all-time total / all-time average (with minimum games)", not only an all-time count. The text
  keeps listing every target. Deaths / near-enemy / push / block rules stay marked "estimated".
- **Merge** On a Roll + Unstoppable into one ladder; **replace** Versatile Bot's "in one day" with "days using all 12".
  These change what two or three existing ids mean (see risks).
- Frontend: nothing structural (platinum / diamond frames and "12 / 25 for platinum" already exist); the legend text
  ("white 25 %, bronze 50 %...") changes to describe medals; an "earned medals" count replaces "Completed (gold / diamond)".
- Rarity: "unlocked" = bronze for tiered rules (already so); add per-medal shares to the catalogue.
- Tests: `test_achievements.py` (catalogue size / ids, tier tests), version bump, Changelog, Decisions entry (D-number),
  DataModel.MD line about tiers.

## Risks to know before approving
- **Everyone who "completed" a converted rule drops to gold (60 % progress)** instead of 100 %, because diamond is now
  the top. Overall % falls for everybody; nothing is lost, the ladder just has more steps above. The launch date for
  achievements is still in the future (Coming soon page), so no live players are affected; confirm that is still the
  case.
- A few rules change meaning slightly: Versatile Bot (days), the win-streak merge (two ids become one), "3 or fewer deaths"
  (counts games instead of the best one).
- Near-enemy and near-teammate ladders are chosen to spread players out; they will look very different from the old
  "2 % / 22 % / 13 %" texts. The website text is the spec, so the new texts will have to be shown in full.
- Unreleased / new gear and Overcharge are too young for good targets: retune after launch.

## Questions for you
1. Approve the whole set as is, or strike / change specific rows (a gold target you disagree with, a new challenge you do
   not want)?
2. Merge On a Roll + Unstoppable into "Win Streak"? (otherwise they stay single-step, 5 and 10 wins in a row.)
3. Pew Pew Proof: leave single-step, or give it a ladder anyway (e.g. average under 8 / 6 / 5 / 4 / 3 deaths in a week of 25+ games)?
4. Add Winning Habit (win rate)? I recommend not.
5. Raise Clean Sweep / Special Delivery diamond from 50 to 100? (3.3 % currently reach it for Clean Sweep.)

## Review outcome (user, 2026-10-31) — supersedes the tables above where different
Approved as proposed: gear veterans, Gearhead, all-64 loadouts, Versatile Bot (days), map games (day / week / all time),
Capture Point / Payload games (day / week / all time), Combat pubs (day / week / all time), per-game teammate / enemy /
inverted %, deaths rules, weekly and all-time averages, Centurion, Hold the Line (defence-win count), Pedal to the Metal,
Immovable Object, Freight Train, emotes, unreleased gear (low ladders, retune later), and merging On a Roll + Unstoppable
into **Win Streak 3/5/8/12/16**.

Changed by the user:
- Use only X **in one day**: **3 / 6 / 10 / 15 / 20** games (gold 10, easier than today's 15).
- Use only X **in one week**: **5 / 10 / 15 / 30 / 50** games (gold 15, easier than today's 20).
- Top speed in one game: **14 / 18 / 22 / 26 / 32** m/s.
- Clean Sweep and Special Delivery diamond raised: **1 / 5 / 10 / 25 / 100**.

Left single-step: Pew Pew Proof (43), Jack of All Trades, Ordnance Sampler, Tac Mod Tinkerer, Beam Me Up, Arsenal Overload,
Ordnance Overload, Forbidden Arsenal.

New challenges approved: Frequent Flyer, Regular, Loyal Bot, Daily Grind, Time Well Wasted, Overtime, Hot Day, Point Taker,
Cargo Hauler, Grand Tour, Weapons Master, Loadout Scholar, Immovable Object, Medal Collector (sized after implementation).
Not added: Winning Habit (win rate).
