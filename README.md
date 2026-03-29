# Automatic Replay Compiler API 

A REST API that ingests match simulation data from [Pokémon Showdown](https://pokemonshowdown.com/) every 30 minutes and exposes statistics on those matches, like the most used pokemon in a format, or the top ranked matches of the day. It also allows you to search matches by players or teams. 

See it in use on our website [ArcVGC](https://arcvgc.com/). Look out for our Android and iOS apps coming soon!

**Current formats supported:** [Gen 9] VGC 2026 Reg F, [Gen 9] VGC 2026 Reg I. More formats coming soon!

---

## Base URL & Versioning


https://arcvgc.com/api/v1/


⚠️ **v0 is deprecated** and will be removed in a future release. Please use `/api/v1/`. See response headers on v0 endpoints for details.

All endpoints return JSON. No authentication is required.

---

## API Docs
More detail is coming soon, but in the meantime, see our docs page at https://arcvgc.com/api/v1/docs

---


## Frontend Codebase

https://github.com/rowanwhall/ARCVGC

---

## Acknowledgments
Thank you to Pokemon Showdown for providing the match data backing our stats, and [Serebii](https://www.serebii.net/) for data on pokemon, moves, abilities, items, and types.

---

## Legal
ARC is not affiliated with Nintendo, The Pokémon Company, Game Freak, Creatures Inc., or Pokémon Showdown/Smogon.
