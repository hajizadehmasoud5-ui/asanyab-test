# DrLinq Patient Product Blueprint

Research date: 2026-08-28

## Product conclusion

DrLinq V1 should not imitate a full appointment marketplace before it has provider-controlled availability. Its immediate job is narrower and valuable: turn a plain-language patient need into a small, honest list of real providers in the selected city, with insurance evidence, contact details, source provenance, and a fast next action. The marketplace layer should be added only after the patient search works reliably.

## Patterns observed

| Pattern | Strong examples | DrLinq implication |
|---|---|---|
| Search starts with need, symptom, procedure, specialty, or provider name | Zocdoc, Doctolib, Healthgrades, DoktorTakvimi | Use a patient-friendly service field with aliases; do not require medical terminology. |
| Location is a first-class input | All reviewed products | Ask province/city early; district remains optional and only appears where data supports it. |
| Insurance is useful but optional | Zocdoc, Vezeeta, Healthgrades | Offer «بیمه ندارم / آزاد» and never block search on insurance. |
| Results explain why a provider matched | Zocdoc, insurer directories | Show matched service, city, insurer, verification/source, and freshness—without inventing availability. |
| Provider cards optimize the next action | Zocdoc, Vezeeta, Doctolib, Okadoc | V1 CTA is Call or View details; booking appears only after real availability exists. |
| Trust is operational, not decorative | Zocdoc, Vezeeta, Doctolib | Verification must mean a traceable source or completed provider verification. No fake ratings, badges, or statistics. |
| No-result recovery changes one constraint at a time | NHS service finders and mature marketplace filters | Suggest removing insurance, broadening the service, or trying a nearby city; never fabricate a result. |
| Return value comes from saved context and follow-up | Doctolib, Practo | Later phases can add saved insurance/location, request status, reminders, and care history. |
| A directory becomes a marketplace when supply responds | Zocdoc, Doctolib, Vezeeta, WhatClinic | Future provider flow: relevant request → interested/unavailable → time/price note → patient selects. |

## What to copy conceptually

- One dominant task on the home page: «برای درمانم کجا بروم؟»
- A two-step mobile flow: need first, location second; insurance is an optional refinement.
- Search suggestions that accept everyday Persian and map it to a controlled service taxonomy.
- Result cards that expose the match evidence and the strongest real CTA.
- A compact details page with service, insurer, address, phone, source, and verification date.
- Visible edit-search, loading, API-error, and honest empty states.
- Configuration-based brand/locale so Arabic and a future rename do not require a rebuild.

## What not to build in V1

- No generic symptom checker, diagnosis, treatment advice, or AI chat on the homepage.
- No fake appointment slots, prices, reviews, provider photos, popularity, or «best doctor» claims.
- No provider CRM, payment, chat, or referral commission system before patient search is proven.
- No map dependency where coordinates are incomplete; address and city must remain usable alone.
- No mandatory account, phone, budget, or medical-history form before results.
- No paid SaaS or new infrastructure when the existing API/VPS can serve the experience.

## Proposed patient journey

1. **Home:** patient describes the service/treatment in everyday Persian.
2. **Location:** province and city; use previous choice when available, but allow editing.
3. **Insurance:** optional insurer or «آزاد / بدون بیمه».
4. **Matching:** normalize the need, query the real provider bank, and rank exact matches first.
5. **Results:** show the applied filters, result count, evidence-backed cards, and edit controls.
6. **Details:** show all available verified fields and source freshness.
7. **Action:** call when a real phone exists; otherwise only show details/source.
8. **No result:** offer one-click legitimate relaxations and explain coverage honestly.

Target: useful results within 30–60 seconds and no more than three required decisions.

## Information architecture

- `/` — patient search and simple product explanation
- `/results` — filtered providers, search editing, empty/error/loading states
- `/provider/:id` — provider details and source/verification evidence
- `/about-data` — data coverage, verification meaning, and correction channel
- `/health` — deployment health endpoint
- Future modules (not V1 navigation): `/request/:id`, `/provider-portal`, `/provider/respond/:token`

## Minimum useful feature set

- Mobile-first Persian RTL UI with keyboard-safe, touch-friendly controls.
- Service taxonomy plus normalized aliases and typo-tolerant matching where practical.
- Province → city dependency and optional insurer filter.
- Real API/provider-bank integration; no demo fallback presented as real data.
- Deduplication and deterministic ranking: exact service + exact city + insurer, then broader valid matches.
- Provider card and detail page with graceful handling of missing fields.
- Source URL, source type/status, and last verification date when present.
- Call action only for valid phone data.
- Honest coverage disclosure and no-result recovery actions.
- Brand/locale/runtime API configuration.
- Automated tests for dental, laboratory, free/no-insurance, no-result, multiple-result, and API-failure cases.

## Phase 2 boundary

Once the patient flow passes real-data tests, add only the request/response backbone: a structured patient request, deterministic provider matching, provider notification, interested/unavailable response, optional availability/price/note, patient comparison, and selection. Keep it separate from provider-bank records so a later n8n workflow can consume events without changing the patient search model.

## Research sources

- [Zocdoc — how search works](https://www.zocdoc.com/patient-help/en/articles/8975433-how-does-search-work-on-zocdoc)
- [Zocdoc — insurance search](https://www.zocdoc.com/patient-help/en/articles/8733187-how-do-i-find-a-doctor-who-takes-my-insurance)
- [Doctolib patient search](https://www.doctolib.com/)
- [Doctolib booking flow](https://doctolibpatient.zendesk.com/hc/de/articles/14141893264924-How-can-I-book-an-appointment-online)
- [Vezeeta — patient marketplace](https://www.vezeeta.com/en)
- [Vezeeta — insurance directory](https://www.vezeeta.com/en/insurances)
- [Practo — care marketplace](https://www.practo.com/)
- [DoktorTakvimi — Turkey](https://www.doktortakvimi.com/)
- [WhatClinic — treatment-led clinic marketplace](https://www.whatclinic.com/)
- [Okadoc — Gulf appointment marketplace](https://www.okadoc.com/)
- [NHS Service Finder](https://digital.nhs.uk/services/nhs-service-finder)
- [Healthgrades search methodology](https://www.healthgrades.com/about/healthgrades-methodologies)
