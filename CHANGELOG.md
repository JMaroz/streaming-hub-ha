# Changelog

## [2.7.0](https://github.com/JMaroz/streaming-hub-ha/compare/v2.6.1...v2.7.0) (2026-10-04)


### Features

* **anime:** add dedicated anime streaming engine and source adapter ([de2c58a](https://github.com/JMaroz/streaming-hub-ha/commit/de2c58aec89bcaf30ba0c62203ad189c8d1cf202))


### Bug Fixes

* **player:** prevent premature outro cut-off and season loop on series completion ([193b4f0](https://github.com/JMaroz/streaming-hub-ha/commit/193b4f024278ade87ff26494d3be0f7d6194dc12))

## [2.6.1](https://github.com/JMaroz/streaming-hub-ha/compare/v2.6.0...v2.6.1) (2026-10-03)


### Bug Fixes

* **catalog:** resolve home carousels and latest arrivals grid coexistence ([f9d1e56](https://github.com/JMaroz/streaming-hub-ha/commit/f9d1e56dd30b64ea5c54738a50561d3ba811e547))

## [2.6.0](https://github.com/JMaroz/streaming-hub-ha/compare/v2.5.1...v2.6.0) (2026-10-03)


### Features

* **catalog:** introduce home editorial carousels and hero banner revision ([3a0440b](https://github.com/JMaroz/streaming-hub-ha/commit/3a0440bd593d31a08b2ae1b3f582202040f3eb13))
* **catalog:** preload streaming providers for visible cards and group platforms ([ea00049](https://github.com/JMaroz/streaming-hub-ha/commit/ea00049b35d693d8f74455eea26e147dbaee83e5))
* **ui:** integrate project brand logo and unify neon cyber-cinematic theme ([06bf009](https://github.com/JMaroz/streaming-hub-ha/commit/06bf009f112cb284f18698d59d1ec4184fcc6796))

## [2.5.1](https://github.com/JMaroz/streaming-hub-ha/compare/v2.5.0...v2.5.1) (2026-10-03)


### Bug Fixes

* **proxy:** add image proxy endpoint and wrapper to fix broken external posters ([b648351](https://github.com/JMaroz/streaming-hub-ha/commit/b64835155c6f520ce22b049f32ea79436dff5f38))

## [2.5.0](https://github.com/JMaroz/streaming-hub-ha/compare/v2.4.0...v2.5.0) (2026-10-02)


### Features

* **catalog:** add dynamic metadata refresh, TTL invalidation, and 12h background sync ([8b0d385](https://github.com/JMaroz/streaming-hub-ha/commit/8b0d38530efb131317f985ef7657478a945d9ea9))


### Bug Fixes

* **cast:** prioritize genuine Cast devices and eliminate invalid url mime fallback ([4fc3ddc](https://github.com/JMaroz/streaming-hub-ha/commit/4fc3ddcb1aecf228e56097fb92ebb0dc325b3637))

## [2.4.0](https://github.com/JMaroz/streaming-hub-ha/compare/v2.3.0...v2.4.0) (2026-10-02)


### Features

* **player:** add smart credits detection, skip intro, and isolate watch progress ([1e4e613](https://github.com/JMaroz/streaming-hub-ha/commit/1e4e61338ec74e962e503f727e42e220afb7f702))

## [2.3.0](https://github.com/JMaroz/streaming-hub-ha/compare/v2.2.1...v2.3.0) (2026-10-01)


### Features

* **player:** add smart subtitles, auto-next episode, failover and HA cinema events ([a1fad86](https://github.com/JMaroz/streaming-hub-ha/commit/a1fad8690f4a9a5b0a76044e491b496913c9f677))


### Bug Fixes

* **history:** restore watch progress tracking and continue watching shelf ([58cb3ea](https://github.com/JMaroz/streaming-hub-ha/commit/58cb3ea542db3cf91f66144d3ffe0ae8f107307e))

## [2.2.1](https://github.com/JMaroz/streaming-hub-ha/compare/v2.2.0...v2.2.1) (2026-09-30)


### Bug Fixes

* **rating:** prevent adult content leakage in kids profiles ([76c8fd5](https://github.com/JMaroz/streaming-hub-ha/commit/76c8fd52dded3fcd2e01e03e9017c95cb34e910a))

## [2.2.0](https://github.com/JMaroz/streaming-hub-ha/compare/v2.1.0...v2.2.0) (2026-09-30)


### Features

* **settings:** add TMDb API key validation and watch providers cache re-enrichment ([26f4a7d](https://github.com/JMaroz/streaming-hub-ha/commit/26f4a7d4dfdc70cc01fc714e84c27127c1b7097e))

## [2.1.0](https://github.com/JMaroz/streaming-hub-ha/compare/v2.0.0...v2.1.0) (2026-09-30)


### Features

* **streaming:** add geolocated streaming availability and overhaul content badges ([fdab78c](https://github.com/JMaroz/streaming-hub-ha/commit/fdab78c3f03172a77645ef8da029871f95aa9bac))

## [2.0.0](https://github.com/JMaroz/streaming-hub-ha/releases/tag/v2.0.0) (2026-09-29)

### Features & Refactoring

* **core:** introduce generic reactive and crawler streaming engines with automatic heuristic detection
* **db:** migrate SQLite models to generic source attributes with non-destructive fallback
* **proxy:** optimize HLS stream proxy with accurate HEAD probe lengths and MIME classification
* **cast:** full Google Cast and ExoPlayer compatibility with interactive floating control bar
* **profile:** multi-profile family accounts, strict PEGI ratings, and Trakt.tv synchronization
* **tools:** standalone playback debugger CLI script and comprehensive troubleshooting guides
