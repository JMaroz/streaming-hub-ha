/**
 * Streaming Hub - Frontend Application Logic
 */

(function () {
  "use strict";

  function getProxiedImageUrl(url) {
    if (!url) return "";
    if (url.startsWith("data:")) return url;
    if (url.includes("image.tmdb.org")) return url;
    if (url.includes("unsplash.com")) return url;
    return `${state.ingressPath}/api/proxy/image?url=${encodeURIComponent(url)}`;
  }


  // Application State
  const state = {
    activeProfileId: localStorage.getItem("streaming_hub_active_profile_id") || "default",
    profiles: [],
    favoritesSet: new Set(),
    activeType: "all",
    animeDubFilter: "all",
    activeGenre: null,
    activeSource: "all",
    availableSources: [],
    searchQuery: "",
    catalogItems: [],
    currentPage: 1,
    hasMore: true,
    isLoadingMore: false,
    activeMode: "latest",
    selectedItem: null,
    selectedSeason: 1,
    selectedEpisode: null,
    selectedSource: null,
    selectedDevice: "browser",
    mediaPlayers: [],
    hls: null,
    ingressPath: "",
    resumeProgress: null,
    playbackSession: null,
    castSession: {
      active: false,
      entityId: null,
      deviceName: null,
      title: null,
      posterUrl: "",
      isTv: false,
      season: null,
      episode: null,
      state: "idle",
      position: 0,
      duration: 0,
      volume: 1,
      muted: false,
      isSeeking: false,
      pollTimer: null,
      localTimer: null,
      idleCount: 0,
    },
  };

  // DOM Elements
  const elements = {
    // Profile controls
    profileDropdownWrapper: document.getElementById("profile-dropdown-wrapper"),
    btnProfilePill: document.getElementById("btn-profile-pill"),
    navProfileAvatar: document.getElementById("nav-profile-avatar"),
    navProfileName: document.getElementById("nav-profile-name"),
    profileDropdownMenu: document.getElementById("profile-dropdown-menu"),
    profilesListMenu: document.getElementById("profiles-list-menu"),
    btnDropdownSwitch: document.getElementById("btn-dropdown-switch"),
    btnDropdownFavorites: document.getElementById("btn-dropdown-favorites"),
    btnDropdownWatched: document.getElementById("btn-dropdown-watched"),

    // Profile Picker Modal
    profilePickerModal: document.getElementById("profile-picker-modal"),
    profilePickerGrid: document.getElementById("profile-picker-grid"),

    // Carousels / Shelves
    continueSection: document.getElementById("continue-section"),
    continueRow: document.getElementById("continue-row"),
    continueCount: document.getElementById("continue-count"),
    favoritesSection: document.getElementById("favorites-section"),
    favoritesRow: document.getElementById("favorites-row"),
    favoritesCount: document.getElementById("favorites-count"),

    btnRestartTrigger: document.getElementById("btn-restart-trigger"),
    brandLogo: document.getElementById("brand-logo"),
    navTabs: document.querySelectorAll(".nav-tab[data-type]"),
    btnGenresToggle: document.getElementById("btn-genres-toggle"),
    genresBar: document.getElementById("genres-bar"),
    genresList: document.getElementById("genres-list"),
    navTabAnime: document.getElementById("nav-tab-anime"),
    sourcesFilterBar: document.getElementById("sources-filter-bar"),
    sourcesChips: document.getElementById("sources-chips"),
    animeFiltersBar: document.getElementById("anime-filters-bar"),
    animeChips: document.getElementById("anime-chips"),
    searchInput: document.getElementById("search-input"),
    searchClear: document.getElementById("search-clear"),
    heroSection: document.getElementById("hero-section"),
    heroBackdrop: document.getElementById("hero-backdrop"),
    heroType: document.getElementById("hero-type"),
    heroRating: document.getElementById("hero-rating"),
    heroYear: document.getElementById("hero-year"),
    heroTitle: document.getElementById("hero-title"),
    heroDescription: document.getElementById("hero-description"),
    heroPlayBtn: document.getElementById("hero-play-btn"),
    heroFavoriteBtn: document.getElementById("hero-favorite-btn"),
    heroInfoBtn: document.getElementById("hero-info-btn"),
    sectionTitle: document.getElementById("section-title"),
    sectionCount: document.getElementById("section-count"),
    homeCarouselsSection: document.getElementById("home-carousels-section"),
    catalogCarousels: document.getElementById("catalog-carousels"),
    catalogGrid: document.getElementById("catalog-grid"),
    loadingSpinner: document.getElementById("loading-spinner"),
    emptyState: document.getElementById("empty-state"),
    detailsModal: document.getElementById("details-modal"),
    modalClose: document.getElementById("modal-close"),
    modalBackdropClose: document.getElementById("modal-backdrop-close"),
    modalBackdropImg: document.getElementById("modal-backdrop-img"),
    modalPoster: document.getElementById("modal-poster"),
    modalTitle: document.getElementById("modal-title"),
    modalYear: document.getElementById("modal-year"),
    modalDuration: document.getElementById("modal-duration"),
    modalRating: document.getElementById("modal-rating"),
    modalCert: document.getElementById("modal-cert"),
    modalTypeBadge: document.getElementById("modal-type-badge"),
    modalUpdateChip: document.getElementById("modal-update-chip"),
    modalUpdateChipText: document.getElementById("modal-update-chip-text"),
    modalGenres: document.getElementById("modal-genres"),
    modalPlot: document.getElementById("modal-plot"),
    modalCastSection: document.getElementById("modal-cast-section"),
    modalCastText: document.getElementById("modal-cast-text"),
    modalWatchProviders: document.getElementById("modal-watch-providers"),
    providersCountryBadge: document.getElementById("providers-country-badge"),
    providersList: document.getElementById("providers-list"),
    justwatchLink: document.getElementById("justwatch-link"),
    tvSeriesSection: document.getElementById("tv-series-section"),
    seasonsTabs: document.getElementById("seasons-tabs"),
    episodesList: document.getElementById("episodes-list"),
    sourcesSection: document.getElementById("sources-section"),
    sourceSelect: document.getElementById("source-select"),
    deviceSelect: document.getElementById("device-select"),
    btnPlayTrigger: document.getElementById("btn-play-trigger"),
    btnPlayText: document.getElementById("btn-play-text"),
    btnFavoriteTrigger: document.getElementById("btn-favorite-trigger"),
    playerModal: document.getElementById("player-modal"),
    playerCloseBtn: document.getElementById("player-close-btn"),
    playerFullscreenBtn: document.getElementById("player-fullscreen-btn"),
    playerSubtitlesBtn: document.getElementById("player-subtitles-btn"),
    subtitlesMenu: document.getElementById("subtitles-menu"),
    subtitlesList: document.getElementById("subtitles-list"),
    btnSkipIntro: document.getElementById("btn-skip-intro"),
    nextEpisodeOverlay: document.getElementById("next-episode-overlay"),
    nextEpTitle: document.getElementById("next-ep-title"),
    nextEpDesc: document.getElementById("next-ep-desc"),
    btnNextEpPlay: document.getElementById("btn-next-ep-play"),
    btnNextEpCancel: document.getElementById("btn-next-ep-cancel"),
    nextEpCountdown: document.getElementById("next-ep-countdown"),
    playerTitle: document.getElementById("player-title"),
    videoContainer: document.querySelector(".video-container"),
    videoElement: document.getElementById("video-element"),
    playerSpinner: document.getElementById("player-spinner"),
    toastContainer: document.getElementById("toast-container"),
    onboardingState: document.getElementById("onboarding-state"),

    // Cast Control Bar
    castBar: document.getElementById("cast-bar"),
    castNextEpisodeBanner: document.getElementById("cast-next-episode-banner"),
    castNextEpTitle: document.getElementById("cast-next-ep-title"),
    btnCastNextPlay: document.getElementById("btn-cast-next-play"),
    castNextCountdown: document.getElementById("cast-next-countdown"),
    btnCastNextCancel: document.getElementById("btn-cast-next-cancel"),
    castBarPoster: document.getElementById("cast-bar-poster"),
    castBarTitle: document.getElementById("cast-bar-title"),
    castBarBadge: document.getElementById("cast-bar-badge"),
    castBarDevice: document.getElementById("cast-bar-device"),
    castBarStatusDot: document.getElementById("cast-bar-status-dot"),
    castBarStatus: document.getElementById("cast-bar-status"),
    castBarSeekBack: document.getElementById("cast-bar-seek-back"),
    castBarPlayPause: document.getElementById("cast-bar-play-pause"),
    castIconPlay: document.getElementById("cast-icon-play"),
    castIconPause: document.getElementById("cast-icon-pause"),
    castBarSeekForward: document.getElementById("cast-bar-seek-forward"),
    castBarNextEp: document.getElementById("cast-bar-next-ep"),
    castBarCurTime: document.getElementById("cast-bar-cur-time"),
    castBarSlider: document.getElementById("cast-bar-slider"),
    castBarSliderFill: document.getElementById("cast-bar-slider-fill"),
    castBarTotalTime: document.getElementById("cast-bar-total-time"),
    castBarMute: document.getElementById("cast-bar-mute"),
    castIconVol: document.getElementById("cast-icon-vol"),
    castIconVolMute: document.getElementById("cast-icon-vol-mute"),
    castBarVolSlider: document.getElementById("cast-bar-vol-slider"),
    castBarStop: document.getElementById("cast-bar-stop"),

    // Settings & TMDb Validation
    btnDropdownSettings: document.getElementById("btn-dropdown-settings"),
    settingsModal: document.getElementById("settings-modal"),
    settingsModalBackdrop: document.getElementById("settings-modal-backdrop"),
    settingsModalClose: document.getElementById("settings-modal-close"),
    tmdbStatusBadge: document.getElementById("tmdb-status-badge"),
    tmdbKeyInput: document.getElementById("tmdb-key-input"),
    btnToggleKeyVisibility: document.getElementById("btn-toggle-key-visibility"),
    btnValidateTmdb: document.getElementById("btn-validate-tmdb"),
    tmdbValidationResult: document.getElementById("tmdb-validation-result"),
    btnSyncCatalog: document.getElementById("btn-sync-catalog"),
    catalogSyncResult: document.getElementById("catalog-sync-result"),
    tmdbAccountBadge: document.getElementById("tmdb-account-badge"),
    tmdbAccountConnectedBox: document.getElementById("tmdb-account-connected-box"),
    tmdbAccountLoginBox: document.getElementById("tmdb-account-login-box"),
    tmdbAccountUsername: document.getElementById("tmdb-account-username"),
    btnTmdbLogin: document.getElementById("btn-tmdb-login"),
    btnTmdbCompleteLogin: document.getElementById("btn-tmdb-complete-login"),
    btnTmdbSyncAccount: document.getElementById("btn-tmdb-sync-account"),
    btnTmdbDisconnect: document.getElementById("btn-tmdb-disconnect"),
    tmdbAccountResult: document.getElementById("tmdb-account-result"),
  };

  // Helper: Format base API URL respecting Ingress
  function apiUrl(endpoint) {
    const cleanEndpoint = endpoint.startsWith("/") ? endpoint.slice(1) : endpoint;
    let base = state.ingressPath;
    if (!base) {
      base = window.location.pathname || "/";
    }
    if (!base.endsWith("/")) {
      base += "/";
    }
    return `${base}${cleanEndpoint}`;
  }

  // Initialize
  async function init() {
    setupEventListeners();
    await checkStatus();
    const needsPicker = await loadProfiles();
    loadPlayers();
    loadGenres();
    await loadSources();
    if (!needsPicker) {
      refreshAllShelves();
      loadCatalog();
      checkActiveCastSession();
    }
  }

  // Status Check
  async function checkStatus() {
    try {
      const resp = await fetch(apiUrl("api/status"));
      if (resp.ok) {
        const data = await resp.json();
        if (data.ingress_path) {
          state.ingressPath = data.ingress_path;
        }
      }
    } catch (err) {
      console.warn("Could not check status:", err);
    }
  }

  // Event Listeners
  function setupEventListeners() {
    // Infinite Scroll Handler
    let isScrollDebounced = false;
    window.addEventListener("scroll", () => {
      if (isScrollDebounced || state.isLoadingMore || !state.hasMore) return;
      if (state.activeMode !== "latest" && state.activeMode !== "genre") return;

      const scrollPosition = window.innerHeight + window.scrollY;
      const threshold = document.body.offsetHeight - 600;

      if (scrollPosition >= threshold) {
        isScrollDebounced = true;
        setTimeout(() => {
          isScrollDebounced = false;
        }, 250);

        state.isLoadingMore = true;
        const nextPage = state.currentPage + 1;

        if (state.activeMode === "genre" && state.activeGenre) {
          loadByGenre(state.activeGenre, nextPage, true)
            .then(() => {
              state.currentPage = nextPage;
            })
            .finally(() => {
              state.isLoadingMore = false;
            });
        } else if (state.activeMode === "latest") {
          loadCatalog(nextPage, true)
            .then(() => {
              state.currentPage = nextPage;
            })
            .finally(() => {
              state.isLoadingMore = false;
            });
        }
      }
    });

    // Navigation Tabs
    elements.navTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        elements.navTabs.forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        state.activeType = tab.dataset.type;
        state.activeGenre = null;
        updateGenreChipsUI();
        loadCatalog();
      });
    });

    // Genres Toggle
    elements.btnGenresToggle.addEventListener("click", () => {
      elements.genresBar.classList.toggle("hidden");
    });

    // Anime Audio Filter Chips
    if (elements.animeChips) {
      elements.animeChips.querySelectorAll(".source-chip").forEach((chip) => {
        chip.addEventListener("click", () => {
          elements.animeChips.querySelectorAll(".source-chip").forEach((c) => c.classList.remove("active"));
          chip.classList.add("active");
          state.animeDubFilter = chip.dataset.dub || "all";
          loadCatalog();
        });
      });
    }

    // Search Input with Debounce
    let searchTimeout = null;
    elements.searchInput.addEventListener("input", (e) => {
      const val = e.target.value.trim();
      state.searchQuery = val;
      elements.searchClear.classList.toggle("hidden", !val);

      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        if (val.length > 0) {
          executeSearch(val);
        } else {
          loadCatalog();
        }
      }, 350);
    });

    elements.searchClear.addEventListener("click", () => {
      elements.searchInput.value = "";
      state.searchQuery = "";
      elements.searchClear.classList.add("hidden");
      loadCatalog();
    });

    // Logo Click
    elements.brandLogo.addEventListener("click", () => {
      state.activeType = "all";
      state.activeGenre = null;
      state.searchQuery = "";
      elements.searchInput.value = "";
      elements.searchClear.classList.add("hidden");
      elements.navTabs.forEach((t) => t.classList.toggle("active", t.dataset.type === "all"));
      updateGenreChipsUI();
      loadCatalog();
    });

    // Modal Close
    elements.modalClose.addEventListener("click", closeModal);
    elements.modalBackdropClose.addEventListener("click", closeModal);

    // Player Close & Fullscreen
    elements.playerCloseBtn.addEventListener("click", closePlayer);
    if (elements.playerFullscreenBtn) {
      elements.playerFullscreenBtn.addEventListener("click", toggleFullscreen);
    }
    if (elements.videoElement) {
      elements.videoElement.addEventListener("dblclick", (e) => {
        e.preventDefault();
        toggleFullscreen();
      });
    }
    if (elements.videoContainer) {
      elements.videoContainer.addEventListener("dblclick", (e) => {
        if (e.target.closest("button") || e.target.closest(".next-episode-overlay")) return;
        toggleFullscreen();
      });
    }

    const syncFullscreenState = () => {
      const fullEl = document.fullscreenElement || document.webkitFullscreenElement;
      if (fullEl === elements.videoElement && elements.playerModal) {
        if (elements.playerModal.requestFullscreen) {
          elements.playerModal.requestFullscreen().catch(() => {});
        }
      }
    };
    document.addEventListener("fullscreenchange", syncFullscreenState);
    document.addEventListener("webkitfullscreenchange", syncFullscreenState);

    // Subtitles Toggle Button
    if (elements.playerSubtitlesBtn) {
      elements.playerSubtitlesBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (elements.subtitlesMenu) {
          elements.subtitlesMenu.classList.toggle("hidden");
        }
      });
    }

    document.addEventListener("click", (e) => {
      if (elements.subtitlesMenu && !elements.subtitlesMenu.contains(e.target) && e.target !== elements.playerSubtitlesBtn) {
        elements.subtitlesMenu.classList.add("hidden");
      }
    });

    // Next Episode Actions
    if (elements.btnNextEpPlay) {
      elements.btnNextEpPlay.addEventListener("click", () => {
        playPendingNextEpisode();
      });
    }

    if (elements.btnNextEpCancel) {
      elements.btnNextEpCancel.addEventListener("click", () => {
        cancelPendingNextEpisode();
      });
    }

    // Skip Intro Action
    if (elements.btnSkipIntro) {
      elements.btnSkipIntro.addEventListener("click", () => {
        skipIntroAction();
      });
    }

    // Cast Next Episode Actions
    if (elements.btnCastNextPlay) {
      elements.btnCastNextPlay.addEventListener("click", () => {
        triggerNextEpisodeAction("play_now");
      });
    }

    if (elements.btnCastNextCancel) {
      elements.btnCastNextCancel.addEventListener("click", () => {
        triggerNextEpisodeAction("cancel");
      });
    }

    // Play Button Trigger
    elements.btnPlayTrigger.addEventListener("click", handlePlayAction);

    // Favorite Modal Trigger
    if (elements.btnFavoriteTrigger) {
      elements.btnFavoriteTrigger.addEventListener("click", () => {
        if (state.selectedItem) {
          toggleFavoriteItem(state.selectedItem);
        }
      });
    }

    // Modal Update Chip Trigger (Refresh Title / Season Metadata)
    if (elements.modalUpdateChip) {
      elements.modalUpdateChip.addEventListener("click", handleRefreshDetailsAction);
    }

    // Hero Favorite Button
    if (elements.heroFavoriteBtn) {
      elements.heroFavoriteBtn.addEventListener("click", () => {
        if (state.catalogItems && state.catalogItems.length > 0) {
          toggleFavoriteItem(state.catalogItems[0]);
        }
      });
    }

    // Restart Button Trigger (from 0:00)
    if (elements.btnRestartTrigger) {
      elements.btnRestartTrigger.addEventListener("click", () => {
        state.resumeProgress = null;
        elements.btnRestartTrigger.classList.add("hidden");
        const isTv = state.selectedItem && (state.selectedItem.type === "tv" || !!state.selectedItem.seasons);
        if (isTv && state.selectedItem.seasons && state.selectedItem.seasons.length > 0) {
          const firstSeason = state.selectedItem.seasons[0];
          state.selectedSeason = firstSeason.number;
          renderSeasons(state.selectedItem.seasons, 1, 1);
        }
        updatePlayButtonText();
        handlePlayAction();
      });
    }

    // Device Select Change
    elements.deviceSelect.addEventListener("change", (e) => {
      state.selectedDevice = e.target.value;
      updatePlayButtonText();
    });

    // Profile Dropdown Toggle
    if (elements.btnProfilePill && elements.profileDropdownWrapper) {
      elements.btnProfilePill.addEventListener("click", (e) => {
        e.stopPropagation();
        elements.profileDropdownWrapper.classList.toggle("open");
        elements.profileDropdownMenu.classList.toggle("hidden");
      });

      document.addEventListener("click", (e) => {
        if (!elements.profileDropdownWrapper.contains(e.target)) {
          elements.profileDropdownWrapper.classList.remove("open");
          elements.profileDropdownMenu.classList.add("hidden");
        }
      });
    }

    // Dropdown Actions
    if (elements.btnDropdownSwitch) {
      elements.btnDropdownSwitch.addEventListener("click", () => {
        elements.profileDropdownWrapper.classList.remove("open");
        elements.profileDropdownMenu.classList.add("hidden");
        openProfilePickerModal();
      });
    }

    if (elements.btnDropdownFavorites) {
      elements.btnDropdownFavorites.addEventListener("click", () => {
        elements.profileDropdownWrapper.classList.remove("open");
        elements.profileDropdownMenu.classList.add("hidden");
        switchToTab("favorites");
      });
    }

    if (elements.btnDropdownWatched) {
      elements.btnDropdownWatched.addEventListener("click", () => {
        elements.profileDropdownWrapper.classList.remove("open");
        elements.profileDropdownMenu.classList.add("hidden");
        switchToTab("watched");
      });
    }

    if (elements.btnDropdownSettings) {
      elements.btnDropdownSettings.addEventListener("click", () => {
        if (elements.profileDropdownWrapper) elements.profileDropdownWrapper.classList.remove("open");
        if (elements.profileDropdownMenu) elements.profileDropdownMenu.classList.add("hidden");
        openSettingsModal();
      });
    }

    if (elements.settingsModalClose) {
      elements.settingsModalClose.addEventListener("click", closeSettingsModal);
    }

    if (elements.settingsModalBackdrop) {
      elements.settingsModalBackdrop.addEventListener("click", closeSettingsModal);
    }

    if (elements.btnToggleKeyVisibility && elements.tmdbKeyInput) {
      elements.btnToggleKeyVisibility.addEventListener("click", () => {
        const isPass = elements.tmdbKeyInput.type === "password";
        elements.tmdbKeyInput.type = isPass ? "text" : "password";
        elements.btnToggleKeyVisibility.textContent = isPass ? "🙈" : "👁️";
      });
    }

    if (elements.btnValidateTmdb) {
      elements.btnValidateTmdb.addEventListener("click", () => {
        validateAndSaveTmdbKey();
      });
    }

    if (elements.btnSyncCatalog) {
      elements.btnSyncCatalog.addEventListener("click", () => {
        syncCatalogNow();
      });
    }

    if (elements.btnTmdbLogin) {
      elements.btnTmdbLogin.addEventListener("click", () => {
        startTmdbAuth();
      });
    }

    if (elements.btnTmdbCompleteLogin) {
      elements.btnTmdbCompleteLogin.addEventListener("click", () => {
        completeTmdbAuth();
      });
    }

    if (elements.btnTmdbSyncAccount) {
      elements.btnTmdbSyncAccount.addEventListener("click", () => {
        syncTmdbAccount();
      });
    }

    if (elements.btnTmdbDisconnect) {
      elements.btnTmdbDisconnect.addEventListener("click", () => {
        disconnectTmdbAccount();
      });
    }

    // Cast Control Bar Listeners
    if (elements.castBarPlayPause) {
      elements.castBarPlayPause.addEventListener("click", toggleCastPlayPause);
    }
    if (elements.castBarSeekBack) {
      elements.castBarSeekBack.addEventListener("click", () => seekCastRelative(-10));
    }
    if (elements.castBarSeekForward) {
      elements.castBarSeekForward.addEventListener("click", () => seekCastRelative(30));
    }
    if (elements.castBarNextEp) {
      elements.castBarNextEp.addEventListener("click", () => playPendingCastNextEpisode());
    }
    if (elements.castBarSlider) {
      elements.castBarSlider.addEventListener("input", handleCastSliderInput);
      elements.castBarSlider.addEventListener("change", handleCastSliderChange);
    }
    if (elements.castBarMute) {
      elements.castBarMute.addEventListener("click", toggleCastMute);
    }
    if (elements.castBarVolSlider) {
      elements.castBarVolSlider.addEventListener("input", handleCastVolumeChange);
    }
    if (elements.castBarStop) {
      elements.castBarStop.addEventListener("click", stopCastPlayback);
    }

    // Keyboard Esc
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (elements.profilePickerModal && !elements.profilePickerModal.classList.contains("hidden")) {
          // If a profile is already selected, allow closing picker
          if (state.activeProfileId) {
            elements.profilePickerModal.classList.add("hidden");
          }
        } else if (elements.playerModal && !elements.playerModal.classList.contains("hidden")) {
          closePlayer();
        } else if (elements.detailsModal && !elements.detailsModal.classList.contains("hidden")) {
          closeModal();
        }
      }
    });
  }

  // Switch active tab programmatically
  function switchToTab(type) {
    elements.navTabs.forEach((t) => {
      t.classList.toggle("active", t.dataset.type === type);
    });
    state.activeType = type;
    state.activeGenre = null;
    updateGenreChipsUI();
    loadCatalog();
  }

  // Profile Management
  function getAvatarClass(avatarIndex) {
    const idx = ((parseInt(avatarIndex, 10) || 1) - 1) % 6 + 1;
    return `avatar-bg-${idx}`;
  }

  async function loadProfiles() {
    try {
      const resp = await fetch(apiUrl("api/profiles"));
      if (resp.ok) {
        state.profiles = await resp.json();
      }
    } catch (err) {
      console.warn("Could not load profiles:", err);
      state.profiles = [
        { id: "default", name: "Principale", avatar: 1, rating_filter: "ALL" }
      ];
    }

    if (!state.profiles || state.profiles.length === 0) {
      state.profiles = [
        { id: "default", name: "Principale", avatar: 1, rating_filter: "ALL" }
      ];
    }

    // Check if active profile exists
    const storedId = localStorage.getItem("streaming_hub_active_profile_id");
    const active = state.profiles.find((p) => p.id === storedId) || state.profiles[0];
    state.activeProfileId = active.id;
    localStorage.setItem("streaming_hub_active_profile_id", active.id);

    renderActiveProfileHeader();
    renderProfileDropdown();

    // If first time visit or multiple profiles and user hasn't chosen in this browser session
    const hasChosenThisSession = sessionStorage.getItem("streaming_hub_profile_selected");
    if (!hasChosenThisSession && state.profiles.length > 1) {
      openProfilePickerModal();
      return true; // Picker active: defer heavy catalog loading
    }
    return false;
  }

  function getActiveProfile() {
    return state.profiles.find((p) => p.id === state.activeProfileId) || state.profiles[0] || {
      id: "default",
      name: "Principale",
      avatar: 1,
      rating_filter: "ALL"
    };
  }

  function renderActiveProfileHeader() {
    const profile = getActiveProfile();
    if (elements.navProfileAvatar) {
      elements.navProfileAvatar.className = `profile-avatar-thumb ${getAvatarClass(profile.avatar)}`;
      elements.navProfileAvatar.textContent = (profile.name || "P").charAt(0).toUpperCase();
    }
    if (elements.navProfileName) {
      elements.navProfileName.textContent = profile.name;
    }
  }

  function renderProfileDropdown() {
    if (!elements.profilesListMenu) return;
    elements.profilesListMenu.innerHTML = "";

    state.profiles.forEach((p) => {
      const isCurrent = p.id === state.activeProfileId;
      const row = document.createElement("div");
      row.className = `profile-item-row ${isCurrent ? "active" : ""}`;

      const avatarClass = getAvatarClass(p.avatar);
      const ratingBadge = p.rating_filter && p.rating_filter !== "ALL" ? ` (${p.rating_filter})` : "";

      row.innerHTML = `
        <div class="profile-item-left">
          <div class="profile-avatar-thumb ${avatarClass}">${(p.name || "P").charAt(0).toUpperCase()}</div>
          <div class="profile-name-col">
            <span class="profile-item-name">${escapeHtml(p.name)}</span>
            <span class="profile-rating-badge">${p.rating_filter || "Tutti"}${ratingBadge ? "" : " (Tutti i contenuti)"}</span>
          </div>
        </div>
        ${isCurrent ? '<svg style="width:16px;height:16px;color:var(--primary)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>' : ""}
      `;

      row.addEventListener("click", () => {
        elements.profileDropdownWrapper.classList.remove("open");
        elements.profileDropdownMenu.classList.add("hidden");
        selectProfile(p.id, true);
      });

      elements.profilesListMenu.appendChild(row);
    });
  }

  function openProfilePickerModal() {
    if (!elements.profilePickerModal || !elements.profilePickerGrid) return;
    elements.profilePickerGrid.innerHTML = "";

    state.profiles.forEach((p) => {
      const card = document.createElement("div");
      const isCurrent = p.id === state.activeProfileId;
      card.className = `profile-picker-card ${isCurrent ? "active" : ""}`;

      const avatarClass = getAvatarClass(p.avatar);
      card.innerHTML = `
        <div class="profile-picker-avatar ${avatarClass}">
          ${(p.name || "P").charAt(0).toUpperCase()}
        </div>
        <span class="profile-picker-name">${escapeHtml(p.name)}</span>
        <span class="profile-picker-tag">${p.rating_filter || "ALL"}</span>
      `;

      card.addEventListener("click", () => {
        elements.profilePickerModal.classList.add("hidden");
        selectProfile(p.id, true);
      });

      elements.profilePickerGrid.appendChild(card);
    });

    elements.profilePickerModal.classList.remove("hidden");
  }

  // Settings & TMDb Validation Modal Functions
  let tmdbPendingRequestToken = null;

  async function openSettingsModal() {
    if (!elements.settingsModal) return;
    elements.settingsModal.classList.remove("hidden");
    if (elements.tmdbValidationResult) {
      elements.tmdbValidationResult.classList.add("hidden");
    }
    if (elements.catalogSyncResult) {
      elements.catalogSyncResult.classList.add("hidden");
    }
    if (elements.tmdbAccountResult) {
      elements.tmdbAccountResult.classList.add("hidden");
    }
    await checkTmdbStatus();
    await checkTmdbAccountStatus();
  }

  function closeSettingsModal() {
    if (elements.settingsModal) {
      elements.settingsModal.classList.add("hidden");
    }
  }

  async function checkTmdbStatus() {
    if (!elements.tmdbStatusBadge) return;
    try {
      const resp = await fetch(apiUrl("api/settings/tmdb/validate"));
      if (resp.ok) {
        const data = await resp.json();
        updateTmdbStatusUI(data.valid, data.message, data.configured);
      } else {
        updateTmdbStatusUI(false, "Impossibile verificare lo stato TMDb.");
      }
    } catch (err) {
      console.warn("Error checking TMDb status:", err);
      updateTmdbStatusUI(false, "Errore di connessione.");
    }
  }

  function updateTmdbStatusUI(valid, message, configured = false) {
    if (!elements.tmdbStatusBadge) return;
    if (valid) {
      elements.tmdbStatusBadge.textContent = "ATTIVA E VALIDA";
      elements.tmdbStatusBadge.className = "badge badge-status-valid";
    } else if (configured) {
      elements.tmdbStatusBadge.textContent = "CHIAVE NON VALIDA";
      elements.tmdbStatusBadge.className = "badge badge-status-invalid";
    } else {
      elements.tmdbStatusBadge.textContent = "NON CONFIGURATA";
      elements.tmdbStatusBadge.className = "badge badge-status-missing";
    }
  }

  async function validateAndSaveTmdbKey() {
    if (!elements.tmdbKeyInput || !elements.btnValidateTmdb) return;
    const rawKey = elements.tmdbKeyInput.value.trim();
    if (!rawKey) {
      showValidationResult(false, "Inserisci una chiave API TMDb prima di verificare.");
      return;
    }

    elements.btnValidateTmdb.disabled = true;
    elements.btnValidateTmdb.textContent = "Verifica in corso...";
    if (elements.tmdbValidationResult) {
      elements.tmdbValidationResult.classList.add("hidden");
    }

    try {
      const resp = await fetch(apiUrl("api/settings/tmdb/validate"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: rawKey, save: true }),
      });

      if (resp.ok) {
        const data = await resp.json();
        showValidationResult(data.valid, data.message);
        updateTmdbStatusUI(data.valid, data.message, true);
        if (data.valid) {
          showToast("Chiave TMDb verificata e attivata con successo!", "success");
          elements.tmdbKeyInput.value = "";
        }
      } else {
        showValidationResult(false, "Errore nella richiesta di verifica.");
      }
    } catch (err) {
      console.error("Error validating TMDb key:", err);
      showValidationResult(false, "Errore di connessione durante la verifica.");
    } finally {
      elements.btnValidateTmdb.disabled = false;
      elements.btnValidateTmdb.textContent = "Verifica Chiave";
    }
  }

  function showValidationResult(success, message) {
    if (!elements.tmdbValidationResult) return;
    elements.tmdbValidationResult.textContent = message;
    elements.tmdbValidationResult.className = `validation-result-msg ${success ? "success" : "error"}`;
    elements.tmdbValidationResult.classList.remove("hidden");
  }

  async function checkTmdbAccountStatus() {
    if (!elements.tmdbAccountBadge) return;
    try {
      const resp = await fetch(apiUrl(`api/tmdb/account/status?profile_id=${encodeURIComponent(state.activeProfileId)}`));
      if (resp.ok) {
        const data = await resp.json();
        if (data.connected && data.username) {
          elements.tmdbAccountBadge.textContent = "COLLEGATO";
          elements.tmdbAccountBadge.className = "badge badge-status-valid";
          if (elements.tmdbAccountUsername) {
            elements.tmdbAccountUsername.textContent = `👤 Connesso come: ${data.username}`;
          }
          if (elements.tmdbAccountConnectedBox) elements.tmdbAccountConnectedBox.classList.remove("hidden");
          if (elements.tmdbAccountLoginBox) elements.tmdbAccountLoginBox.classList.add("hidden");
        } else {
          elements.tmdbAccountBadge.textContent = "NON COLLEGATO";
          elements.tmdbAccountBadge.className = "badge badge-status-missing";
          if (elements.tmdbAccountConnectedBox) elements.tmdbAccountConnectedBox.classList.add("hidden");
          if (elements.tmdbAccountLoginBox) elements.tmdbAccountLoginBox.classList.remove("hidden");
          if (elements.btnTmdbLogin) elements.btnTmdbLogin.classList.remove("hidden");
          if (elements.btnTmdbCompleteLogin) elements.btnTmdbCompleteLogin.classList.add("hidden");
        }
      }
    } catch (err) {
      console.warn("Error checking TMDb account status:", err);
    }
  }

  async function syncCatalogNow() {
    if (!elements.btnSyncCatalog) return;
    elements.btnSyncCatalog.disabled = true;
    const originalText = elements.btnSyncCatalog.innerHTML;
    elements.btnSyncCatalog.innerHTML = `<span class="btn-text">⏳ Sincronizzazione in corso...</span>`;
    showCatalogSyncResult(true, "Scansione ed arricchimento del catalogo in corso...");

    try {
      const resp = await fetch(apiUrl("api/metadata/sync-catalog?limit=50"), {
        method: "POST",
      });
      const data = await resp.json();
      if (resp.ok && data.status === "ok") {
        showCatalogSyncResult(true, data.message || "Catalogo sincronizzato con successo!");
        showToast("Sincronizzazione catalogo completata con successo! 🎬", "success");
        loadCatalog(false);
      } else {
        showCatalogSyncResult(false, data.detail || data.message || "Errore durante la sincronizzazione.");
      }
    } catch (err) {
      console.error("Error syncing catalog:", err);
      showCatalogSyncResult(false, "Errore di connessione durante la sincronizzazione.");
    } finally {
      elements.btnSyncCatalog.disabled = false;
      elements.btnSyncCatalog.innerHTML = originalText;
    }
  }

  function showCatalogSyncResult(success, message) {
    if (!elements.catalogSyncResult) return;
    elements.catalogSyncResult.textContent = message;
    elements.catalogSyncResult.className = `validation-result-msg ${success ? "success" : "error"}`;
    elements.catalogSyncResult.classList.remove("hidden");
  }

  async function startTmdbAuth() {
    if (!elements.btnTmdbLogin) return;
    elements.btnTmdbLogin.disabled = true;
    showTmdbAccountResult(true, "Richiesta token di autenticazione a TMDb...");

    try {
      const resp = await fetch(apiUrl(`api/tmdb/auth/request-token?profile_id=${encodeURIComponent(state.activeProfileId)}`), {
        method: "POST",
      });
      const data = await resp.json();
      if (resp.ok && data.success && data.request_token && data.auth_url) {
        tmdbPendingRequestToken = data.request_token;
        window.open(data.auth_url, "_blank");
        if (elements.btnTmdbLogin) elements.btnTmdbLogin.classList.add("hidden");
        if (elements.btnTmdbCompleteLogin) elements.btnTmdbCompleteLogin.classList.remove("hidden");
        showTmdbAccountResult(
          true,
          "Pagina di autorizzazione TMDb aperta in una nuova scheda. Accedi, approva Streaming Hub e poi clicca sul pulsante verde qui sotto."
        );
      } else {
        showTmdbAccountResult(false, data.detail || "Impossibile avviare l'autenticazione con TMDb.");
      }
    } catch (err) {
      console.error("Error starting TMDb auth:", err);
      showTmdbAccountResult(false, "Errore di connessione durante la richiesta token TMDb.");
    } finally {
      elements.btnTmdbLogin.disabled = false;
    }
  }

  async function completeTmdbAuth() {
    if (!tmdbPendingRequestToken || !elements.btnTmdbCompleteLogin) return;
    elements.btnTmdbCompleteLogin.disabled = true;
    showTmdbAccountResult(true, "Verifica sessione in corso...");

    try {
      const resp = await fetch(apiUrl("api/tmdb/auth/session"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_token: tmdbPendingRequestToken,
          profile_id: state.activeProfileId,
        }),
      });
      const data = await resp.json();
      if (resp.ok && data.success) {
        showToast(`Account TMDb collegato con successo! Benvenuto ${data.username}`, "success");
        showTmdbAccountResult(true, `Connesso con successo come ${data.username}!`);
        tmdbPendingRequestToken = null;
        await checkTmdbAccountStatus();
      } else {
        showTmdbAccountResult(
          false,
          data.detail || "Autorizzazione non completata. Verifica di aver cliccato 'Approva' su themoviedb.org e riprova."
        );
      }
    } catch (err) {
      console.error("Error completing TMDb auth:", err);
      showTmdbAccountResult(false, "Errore di connessione durante il completamento.");
    } finally {
      elements.btnTmdbCompleteLogin.disabled = false;
    }
  }

  async function disconnectTmdbAccount() {
    if (!elements.btnTmdbDisconnect) return;
    if (!confirm("Sei sicuro di voler scollegare l'account TMDb da questo profilo?")) return;

    try {
      const resp = await fetch(apiUrl(`api/tmdb/auth/session?profile_id=${encodeURIComponent(state.activeProfileId)}`), {
        method: "DELETE",
      });
      if (resp.ok) {
        showToast("Account TMDb scollegato dal profilo.", "info");
        showTmdbAccountResult(true, "Account TMDb scollegato.");
        await checkTmdbAccountStatus();
      } else {
        showToast("Errore durante la disconnessione.", "error");
      }
    } catch (err) {
      console.error("Error disconnecting TMDb account:", err);
    }
  }

  async function syncTmdbAccount() {
    if (!elements.btnTmdbSyncAccount) return;
    elements.btnTmdbSyncAccount.disabled = true;
    const origText = elements.btnTmdbSyncAccount.innerHTML;
    elements.btnTmdbSyncAccount.innerHTML = `<span class="btn-text">⏳ Sincronizzazione in corso...</span>`;
    showTmdbAccountResult(true, "Sincronizzazione Watchlist e Preferiti con TMDb in corso...");

    try {
      const resp = await fetch(apiUrl("api/tmdb/account/sync"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: state.activeProfileId }),
      });
      const data = await resp.json();
      if (resp.ok && data.status === "ok") {
        showTmdbAccountResult(true, data.message);
        showToast("Watchlist e Preferiti TMDb sincronizzati! ⭐", "success");
        if (state.activeTab === "home") {
          loadFavorites();
        }
      } else {
        showTmdbAccountResult(false, data.detail || data.message || "Errore sincronizzazione account.");
      }
    } catch (err) {
      console.error("Error syncing TMDb account:", err);
      showTmdbAccountResult(false, "Errore di connessione durante la sincronizzazione account.");
    } finally {
      elements.btnTmdbSyncAccount.disabled = false;
      elements.btnTmdbSyncAccount.innerHTML = origText;
    }
  }

  function showTmdbAccountResult(success, message) {
    if (!elements.tmdbAccountResult) return;
    elements.tmdbAccountResult.textContent = message;
    elements.tmdbAccountResult.className = `validation-result-msg ${success ? "success" : "error"}`;
    elements.tmdbAccountResult.classList.remove("hidden");
  }

  async function selectProfile(profileId, force = false) {
    const isSame = state.activeProfileId === profileId;
    if (isSame && !force) {
      sessionStorage.setItem("streaming_hub_profile_selected", "1");
      return;
    }

    state.activeProfileId = profileId;
    localStorage.setItem("streaming_hub_active_profile_id", profileId);
    sessionStorage.setItem("streaming_hub_profile_selected", "1");

    renderActiveProfileHeader();
    renderProfileDropdown();

    const current = getActiveProfile();
    showToast(`Profilo attivo: ${current.name}`, "info");

    // Immediately clear previous content and show loader to prevent showing previous profile data
    elements.catalogGrid.innerHTML = "";
    if (elements.continueRow) elements.continueRow.innerHTML = "";
    if (elements.favoritesRow) elements.favoritesRow.innerHTML = "";
    if (elements.homeCarouselsSection) elements.homeCarouselsSection.classList.add("hidden");
    showLoading(true);

    // Refresh all profile-scoped data immediately
    refreshAllShelves();
    loadCatalog();
    checkActiveCastSession();
  }

  // Load Media Players from Home Assistant
  async function loadPlayers() {
    try {
      const resp = await fetch(apiUrl("api/players"));
      if (resp.ok) {
        state.mediaPlayers = await resp.json();
        renderPlayersSelect();

        // Restore previous selection if it still exists, otherwise fallback to browser
        if (state.selectedDevice && state.selectedDevice !== "browser") {
          const stillExists = state.mediaPlayers.find((p) => p.entity_id === state.selectedDevice);
          if (!stillExists) {
            state.selectedDevice = "browser";
          }
        }
        if (elements.deviceSelect) {
          elements.deviceSelect.value = state.selectedDevice;
        }
        updatePlayButtonText();
      }
    } catch (err) {
      console.warn("Could not load players:", err);
    }
  }

  // Helper: Format raw Home Assistant entity or device names into clean, friendly names
  function formatDeviceName(entityId, rawName) {
    if (rawName && rawName.trim() && !rawName.startsWith("media_player.") && !/tpm191e/i.test(rawName)) {
      return rawName.trim();
    }
    const clean = (rawName || entityId || "").replace(/^media_player\./, "");
    if (/tpm191e/i.test(clean)) {
      return "Philips Smart TV (TPM191E)";
    }
    const formatted = clean
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
    return formatted || "Dispositivo Cast";
  }

  function renderPlayersSelect() {
    elements.deviceSelect.innerHTML = '<option value="browser">💻 Browser Locale (Web Player)</option>';
    if (state.mediaPlayers && state.mediaPlayers.length > 0) {
      const group = document.createElement("optgroup");
      group.label = "📺 Schermi TV & Dispositivi Cast Disponibili";

      state.mediaPlayers.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.entity_id;
        const stateNote = p.state === "off" ? " (Standby)" : "";
        const friendly = formatDeviceName(p.entity_id, p.name);
        opt.textContent = `📺 ${friendly}${stateNote}`;
        group.appendChild(opt);
      });

      elements.deviceSelect.appendChild(group);
    }
  }

  // Load Genres
  async function loadGenres() {
    try {
      const resp = await fetch(apiUrl("api/catalog/genres"));
      if (resp.ok) {
        const genres = await resp.json();
        elements.genresList.innerHTML = "";
        genres.forEach((g) => {
          const chip = document.createElement("button");
          chip.className = "genre-chip";
          chip.textContent = g;
          chip.addEventListener("click", () => {
            if (state.activeGenre === g) {
              state.activeGenre = null;
            } else {
              state.activeGenre = g;
            }
            updateGenreChipsUI();
            if (state.activeGenre) {
              loadByGenre(state.activeGenre);
            } else {
              loadCatalog();
            }
          });
          elements.genresList.appendChild(chip);
        });
      }
    } catch (err) {
      console.warn("Could not load genres:", err);
    }
  }

  function updateGenreChipsUI() {
    const chips = elements.genresList.querySelectorAll(".genre-chip");
    chips.forEach((c) => {
      c.classList.toggle("active", c.textContent === state.activeGenre);
    });
  }

  // Load Available Streaming Sources
  async function loadSources() {
    try {
      const resp = await fetch(apiUrl("api/sources"));
      if (resp.ok) {
        state.availableSources = await resp.json();
        renderSourcesChips();
        const hasAnime = state.availableSources.some((s) => s.id === "anime" && s.enabled);
        if (elements.navTabAnime) {
          elements.navTabAnime.classList.toggle("hidden", !hasAnime);
        }
      }
    } catch (err) {
      console.warn("Could not load sources:", err);
    }
  }

  function renderSourcesChips() {
    if (!elements.sourcesChips) return;
    elements.sourcesChips.innerHTML = "";

    // "Tutte" chip
    const allChip = document.createElement("button");
    allChip.className = `source-chip ${state.activeSource === "all" ? "active" : ""}`;
    allChip.innerHTML = `<span class="source-chip-dot"></span>Tutte`;
    allChip.addEventListener("click", () => {
      if (state.activeSource === "all") return;
      state.activeSource = "all";
      updateSourcesChipsUI();
      triggerCatalogRefresh();
    });
    elements.sourcesChips.appendChild(allChip);

    // Dynamic registered sources
    state.availableSources.forEach((src) => {
      const chip = document.createElement("button");
      chip.className = `source-chip ${state.activeSource === src.id ? "active" : ""}`;
      chip.innerHTML = `<span class="source-chip-dot"></span>${escapeHtml(src.name)}`;
      chip.addEventListener("click", () => {
        if (state.activeSource === src.id) return;
        state.activeSource = src.id;
        updateSourcesChipsUI();
        triggerCatalogRefresh();
      });
      elements.sourcesChips.appendChild(chip);
    });
  }

  function updateSourcesChipsUI() {
    if (!elements.sourcesChips) return;
    const chips = elements.sourcesChips.querySelectorAll(".source-chip");
    chips.forEach((c) => {
      const text = c.textContent.trim();
      if (text === "Tutte") {
        c.classList.toggle("active", state.activeSource === "all");
      } else {
        const found = state.availableSources.find((s) => s.name === text);
        if (found) {
          c.classList.toggle("active", state.activeSource === found.id);
        }
      }
    });
  }

  function triggerCatalogRefresh() {
    if (state.searchQuery && state.searchQuery.trim().length > 1) {
      executeSearch(state.searchQuery.trim());
    } else if (state.activeGenre) {
      loadByGenre(state.activeGenre);
    } else {
      loadCatalog();
    }
  }

  const DEFAULT_POSTER_SVG =
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='450' viewBox='0 0 300 450'%3E%3Crect width='300' height='450' fill='%23182030'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%2364748b' font-family='sans-serif' font-size='18'%3ELocandina non disponibile%3C/text%3E%3C/svg%3E";

  // Load Catalog Titles
  async function loadCatalog(page = 1, append = false) {
    if (!append) {
      state.currentPage = 1;
      state.hasMore = true;
      state.activeMode = "latest";
      showLoading(true);
      elements.emptyState.classList.add("hidden");
    }

    // Manage Carousel Shelves visibility: show carousels on "all", hide on specific tabs or search
    const isHome = state.activeType === "all" && !state.activeGenre && !state.searchQuery;
    if (!isHome) {
      if (elements.continueSection) elements.continueSection.classList.add("hidden");
      if (elements.favoritesSection) elements.favoritesSection.classList.add("hidden");
      if (elements.homeCarouselsSection) elements.homeCarouselsSection.classList.add("hidden");
    } else if (!append) {
      if (elements.continueSection && elements.continueRow && elements.continueRow.children.length > 0) {
        elements.continueSection.classList.remove("hidden");
      }
      if (elements.favoritesSection && elements.favoritesRow && elements.favoritesRow.children.length > 0) {
        elements.favoritesSection.classList.remove("hidden");
      }
    }

    // Tab "favorites"
    if (state.activeType === "favorites") {
      state.activeMode = "favorites";
      state.hasMore = false;
      elements.sectionTitle.textContent = "I Tuoi Preferiti";
      elements.heroSection.classList.add("hidden");
      try {
        const resp = await fetch(apiUrl(`api/favorites?profile_id=${encodeURIComponent(state.activeProfileId)}`));
        if (!resp.ok) throw new Error("Favorites fetch failed");
        const favs = await resp.json();
        state.catalogItems = favs || [];
        renderGrid(state.catalogItems);
      } catch (err) {
        console.error("Error loading favorites tab:", err);
        showToast("Errore nel caricamento dei preferiti", "error");
      } finally {
        showLoading(false);
      }
      return;
    }

    // Tab "watched"
    if (state.activeType === "watched") {
      state.activeMode = "watched";
      state.hasMore = false;
      elements.sectionTitle.textContent = "Titoli Già Visti";
      elements.heroSection.classList.add("hidden");
      try {
        const resp = await fetch(
          apiUrl(`api/history/watched?profile_id=${encodeURIComponent(state.activeProfileId)}&limit=50`)
        );
        if (!resp.ok) throw new Error("Watched fetch failed");
        const watched = await resp.json();
        // Normalize watched items to match catalog item structure
        state.catalogItems = (watched || []).map((w) => ({
          id: w.media_id,
          title: w.title,
          type: w.media_type,
          poster_url: w.poster_url,
          year: w.completed_at ? new Date(w.completed_at).getFullYear() : "",
          rating: "",
          genres: ["Visto"],
        }));
        renderGrid(state.catalogItems);
      } catch (err) {
        console.error("Error loading watched tab:", err);
        showToast("Errore nel caricamento della cronologia visti", "error");
      } finally {
        showLoading(false);
      }
      return;
    }

    if (!state.availableSources || state.availableSources.length === 0) {
      showLoading(false);
      elements.heroSection.classList.add("hidden");
      elements.catalogGrid.innerHTML = "";
      elements.emptyState.classList.add("hidden");
      elements.onboardingState.classList.remove("hidden");
      elements.sectionTitle.textContent = "Configura le tue Sorgenti";
      elements.sectionCount.textContent = "0 sorgenti";
      return;
    }
    elements.onboardingState.classList.add("hidden");

    let titleText = "Ultimi Arrivi";
    if (state.activeType === "movie") titleText = "Ultimi Film";
    if (state.activeType === "tv") titleText = "Ultime Serie TV";
    if (state.activeType === "anime") titleText = "Catalogo Anime";
    elements.sectionTitle.textContent = titleText;

    if (elements.animeFiltersBar && elements.sourcesFilterBar) {
      if (state.activeType === "anime") {
        elements.animeFiltersBar.classList.remove("hidden");
        elements.sourcesFilterBar.classList.add("hidden");
      } else {
        elements.animeFiltersBar.classList.add("hidden");
        elements.sourcesFilterBar.classList.remove("hidden");
      }
    }

    try {
      let homePromise = null;
      if (isHome && page === 1 && !append) {
        // Load Home Thematic Carousels concurrently
        homePromise = fetch(
          apiUrl(
            `api/catalog/home?source=${state.activeSource}&profile_id=${encodeURIComponent(state.activeProfileId)}`
          )
        )
          .then((r) => (r.ok ? r.json() : null))
          .catch((homeErr) => {
            console.warn("Could not load home carousels:", homeErr);
            return null;
          });
      } else if (elements.homeCarouselsSection) {
        elements.homeCarouselsSection.classList.add("hidden");
      }

      let url = apiUrl(
        `api/catalog/latest?type=${state.activeType}&source=${state.activeSource}&page=${page}&profile_id=${encodeURIComponent(state.activeProfileId)}`
      );
      if (state.activeType === "anime" && state.animeDubFilter) {
        url += `&dub=${encodeURIComponent(state.animeDubFilter)}`;
      }
      const resp = await fetch(url);
      if (!resp.ok) throw new Error("Network response was not ok");
      const data = await resp.json();
      const results = data.results || [];

      if (results.length < 10) {
        state.hasMore = false;
      }

      if (append) {
        state.catalogItems = state.catalogItems.concat(results);
        appendGridItems(results);
      } else {
        state.catalogItems = results;
        renderGrid(state.catalogItems);
        if (isHome) {
          const homeData = homePromise ? await homePromise : null;
          if (homeData && homeData.carousels && homeData.carousels.length > 0) {
            renderHomeCarousels(homeData.carousels);
            if (homeData.hero) {
              updateHero(homeData.hero);
            } else if (state.catalogItems.length > 0) {
              updateHero(state.catalogItems[0]);
            }
          } else {
            if (elements.homeCarouselsSection) elements.homeCarouselsSection.classList.add("hidden");
            if (state.catalogItems.length > 0) {
              updateHero(state.catalogItems[0]);
            } else {
              elements.heroSection.classList.add("hidden");
            }
          }
        } else {
          elements.heroSection.classList.add("hidden");
        }
      }
    } catch (err) {
      console.error("Error loading catalog:", err);
      showToast("Errore nel caricamento del catalogo", "error");
    } finally {
      if (!append) showLoading(false);
    }
  }

  // Search
  async function executeSearch(query) {
    state.activeMode = "search";
    state.hasMore = false;
    showLoading(true);
    elements.emptyState.classList.add("hidden");
    elements.heroSection.classList.add("hidden");
    if (elements.continueSection) elements.continueSection.classList.add("hidden");
    if (elements.favoritesSection) elements.favoritesSection.classList.add("hidden");
    if (elements.homeCarouselsSection) elements.homeCarouselsSection.classList.add("hidden");

    elements.sectionTitle.textContent = `Risultati per "${query}"`;

    try {
      const url = apiUrl(
        `api/catalog/search?q=${encodeURIComponent(query)}&type=${state.activeType}&source=${state.activeSource}&profile_id=${encodeURIComponent(state.activeProfileId)}`
      );
      const resp = await fetch(url);
      if (!resp.ok) throw new Error("Search failed");
      const data = await resp.json();
      state.catalogItems = data.results || [];
      renderGrid(state.catalogItems);
    } catch (err) {
      console.error("Error searching:", err);
      showToast("Errore durante la ricerca", "error");
    } finally {
      showLoading(false);
    }
  }

  // Load by Genre
  async function loadByGenre(genre, page = 1, append = false) {
    if (!append) {
      state.currentPage = 1;
      state.hasMore = true;
      state.activeGenre = genre;
      state.activeMode = "genre";
      showLoading(true);
      elements.emptyState.classList.add("hidden");
      elements.heroSection.classList.add("hidden");
      if (elements.continueSection) elements.continueSection.classList.add("hidden");
      if (elements.favoritesSection) elements.favoritesSection.classList.add("hidden");
      if (elements.homeCarouselsSection) elements.homeCarouselsSection.classList.add("hidden");
    }

    elements.sectionTitle.textContent = `Genere: ${genre}`;

    try {
      const type = state.activeType === "tv" ? "tv" : "movie";
      const url = apiUrl(
        `api/catalog/genre/${encodeURIComponent(genre)}?type=${type}&source=${state.activeSource}&page=${page}&profile_id=${encodeURIComponent(state.activeProfileId)}`
      );
      const resp = await fetch(url);
      if (!resp.ok) throw new Error("Genre fetch failed");
      const data = await resp.json();
      const results = data.results || [];

      if (results.length < 10) {
        state.hasMore = false;
      }

      if (append) {
        state.catalogItems = state.catalogItems.concat(results);
        appendGridItems(results);
      } else {
        state.catalogItems = results;
        renderGrid(state.catalogItems);
      }
    } catch (err) {
      console.error("Error loading genre:", err);
      showToast("Errore durante il caricamento del genere", "error");
    } finally {
      if (!append) showLoading(false);
    }
  }

  // Helper to extract canonical provider logos (Zero Extra Cost Rule: only flatrate, free, ads)
  function getDistinctProviderLogos(avail) {
    if (!avail) return [];
    if (avail.grouped_logos && Array.isArray(avail.grouped_logos) && avail.grouped_logos.length > 0) {
      return avail.grouped_logos.slice(0, 4);
    }
    const flat = avail.flatrate || [];
    const ads = avail.ads || [];
    const free = avail.free || [];
    const combined = [...flat, ...ads, ...free];
    const seen = new Set();
    const pLogos = [];

    for (const p of combined) {
      if (!p || (!p.logo_url && !p.logo_path)) continue;
      const name = (p.provider_name || "").toLowerCase().trim();
      let groupKey = name;
      if (name.includes("amazon") || name.includes("prime video") || name.includes("freevee")) groupKey = "amazon";
      else if (name.includes("netflix")) groupKey = "netflix";
      else if (name.includes("disney")) groupKey = "disney";
      else if (name.includes("apple")) groupKey = "apple";
      else if (name.includes("paramount")) groupKey = "paramount";
      else if (name.includes("max") || name.includes("hbo")) groupKey = "max";
      else if (name.includes("raiplay")) groupKey = "raiplay";
      else if (name.includes("infinity") || name.includes("mediaset")) groupKey = "mediaset";
      else if (name.includes("timvision")) groupKey = "timvision";
      else if (name.includes("now") || name.includes("sky go")) groupKey = "now";
      else if (name.includes("discovery")) groupKey = "discovery";

      if (!seen.has(groupKey)) {
        seen.add(groupKey);
        pLogos.push(p);
      }
    }
    return pLogos.slice(0, 4);
  }

  function buildMiniProvidersHtml(avail) {
    const pLogos = getDistinctProviderLogos(avail);
    if (!pLogos || pLogos.length === 0) return "";
    return `
      <div class="card-provider-logos" title="Disponibile in streaming">
        ${pLogos.map((p) => `<img class="mini-provider-logo" src="${p.logo_url || "https://image.tmdb.org/t/p/w200" + p.logo_path}" alt="${escapeHtml(p.provider_name)}" title="${escapeHtml(p.provider_name)}">`).join("")}
      </div>
    `;
  }

  // Pre-loading batch queue & IntersectionObserver for cards on screen
  const pendingBatchQueue = new Map();
  let batchEnrichTimer = null;
  const BATCH_DEBOUNCE_MS = 150;
  const BATCH_MAX_SIZE = 15;

  const visibleCardsObserver = ("IntersectionObserver" in window)
    ? new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const card = entry.target;
            visibleCardsObserver.unobserve(card);
            queueCardForEnrichment(card);
          }
        });
      }, { rootMargin: "200px 0px" })
    : null;

  function observeCardForStreamingAvailability(card, item) {
    if (!visibleCardsObserver) return;
    const avail = item.streaming_availability;
    const logos = getDistinctProviderLogos(avail);
    if (logos.length > 0) return;
    visibleCardsObserver.observe(card);
  }

  function queueCardForEnrichment(card) {
    const id = card.dataset.titleId;
    if (!id) return;
    if (!pendingBatchQueue.has(id)) {
      pendingBatchQueue.set(id, {
        id: id,
        media_type: card.dataset.mediaType || "movie",
        title: card.dataset.title || "",
        year: parseInt(card.dataset.year) || null,
        cards: [card],
      });
    } else {
      pendingBatchQueue.get(id).cards.push(card);
    }

    if (pendingBatchQueue.size >= BATCH_MAX_SIZE) {
      flushPendingBatchQueue();
    } else if (!batchEnrichTimer) {
      batchEnrichTimer = setTimeout(flushPendingBatchQueue, BATCH_DEBOUNCE_MS);
    }
  }

  async function flushPendingBatchQueue() {
    if (batchEnrichTimer) {
      clearTimeout(batchEnrichTimer);
      batchEnrichTimer = null;
    }
    if (pendingBatchQueue.size === 0) return;

    const itemsToProcess = Array.from(pendingBatchQueue.values());
    pendingBatchQueue.clear();

    const payloadItems = itemsToProcess.map((it) => ({
      id: it.id,
      media_type: it.media_type,
      title: it.title,
      year: it.year,
    }));

    try {
      const resp = await fetch(apiUrl("api/catalog/batch-streaming-availability"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile_id: state.activeProfileId || "default",
          items: payloadItems,
        }),
      });

      if (!resp.ok) return;
      const data = await resp.json();
      const results = data.results || {};

      itemsToProcess.forEach((it) => {
        const avail = results[it.id];
        if (!avail) return;

        // Update in-memory items in catalog
        if (state.catalogItems) {
          const matchedItem = state.catalogItems.find((c) => c.id === it.id);
          if (matchedItem) matchedItem.streaming_availability = avail;
        }

        const logosHtml = buildMiniProvidersHtml(avail);
        if (logosHtml) {
          it.cards.forEach((card) => {
            const posterWrap = card.querySelector(".card-poster-wrap");
            if (posterWrap && !posterWrap.querySelector(".card-provider-logos")) {
              const temp = document.createElement("div");
              temp.innerHTML = logosHtml;
              const logosEl = temp.firstElementChild;
              logosEl.classList.add("fade-in");
              posterWrap.appendChild(logosEl);
            }
          });
        }
      });
    } catch (err) {
      console.warn("Failed to batch fetch streaming availability:", err);
    }
  }

  // Create Card Element
  function createCardElement(item) {
    const card = document.createElement("div");
    card.className = "media-card";

    const posterSrc = getProxiedImageUrl(item.poster_url) || DEFAULT_POSTER_SVG;
    const isTv =
      item.type === "tv" ||
      !!item.seasons ||
      (item.genres && item.genres.some((g) => g.toLowerCase().includes("serie")));
    const typeLabel = isTv ? "Serie TV" : "Film";
    const ratingLabel = item.rating ? `★ ${item.rating}` : "";
    const certInfo = formatCertification(item.certification);
    const certBadgeHtml = certInfo
      ? `<span class="card-badge-cert ${certInfo.class}">${escapeHtml(certInfo.text)}</span>`
      : "";

    const displayTitle = getDisplayTitle(item);
    card.dataset.titleId = item.id;
    card.dataset.mediaType = isTv ? "tv" : "movie";
    card.dataset.title = displayTitle;
    card.dataset.year = item.year || "";


    // Mini streaming provider logos overlay on card (Canonical & Deduplicated)
    const avail =
      item.streaming_availability ||
      (item.watch_providers &&
        (item.watch_providers["IT"] || item.watch_providers[Object.keys(item.watch_providers)[0]]));
    const miniProvidersHtml = buildMiniProvidersHtml(avail);

    const isAnime =
      item.is_anime ||
      (item.catalogs && item.catalogs.includes("anime")) ||
      (item.genres && item.genres.includes("Anime"));
    let dubBadgeHtml = "";
    if (isAnime) {
      if (item.dub_type === "dub" || (item.title && item.title.includes("(ITA)"))) {
        dubBadgeHtml = `<span class="card-badge-dub" style="background:#0284c7;color:#fff;font-size:0.7rem;padding:2px 6px;border-radius:4px;font-weight:600;">ITA</span>`;
      } else {
        dubBadgeHtml = `<span class="card-badge-sub" style="background:#7c3aed;color:#fff;font-size:0.7rem;padding:2px 6px;border-radius:4px;font-weight:600;">SUB ITA</span>`;
      }
    }

    card.innerHTML = `
      <div class="card-poster-wrap">
        <img class="card-poster" src="${posterSrc}" alt="${escapeHtml(displayTitle)}" loading="lazy" onerror="this.onerror=null;this.src='${DEFAULT_POSTER_SVG}';">
        <div class="card-badges">
          <span class="card-badge-type">${typeLabel}</span>
          ${dubBadgeHtml}
          ${certBadgeHtml}
          ${ratingLabel ? `<span class="card-badge-rating">${ratingLabel}</span>` : ""}
        </div>
        ${miniProvidersHtml}
      </div>
      <div class="card-info">
        <div class="card-title" title="${escapeHtml(displayTitle)}">${escapeHtml(displayTitle)}</div>
        <div class="card-subtext">
          <span>${item.year || ""}</span>
          <span>${(item.genres && item.genres[0]) || ""}</span>
        </div>
      </div>
    `;

    // Observe card for background pre-loading if streaming availability is not yet loaded
    if (!miniProvidersHtml) {
      observeCardForStreamingAvailability(card, item);
    }

    card.addEventListener("click", () => openDetails(item));
    return card;
  }

  // Render Home Thematic Carousels
  function renderHomeCarousels(carousels) {
    if (!elements.catalogCarousels) return;
    if (!carousels || carousels.length === 0) {
      if (elements.homeCarouselsSection) elements.homeCarouselsSection.classList.add("hidden");
      elements.catalogCarousels.innerHTML = "";
      return;
    }

    elements.catalogCarousels.innerHTML = "";
    if (elements.homeCarouselsSection) elements.homeCarouselsSection.classList.remove("hidden");

    const fragment = document.createDocumentFragment();
    (carousels || []).forEach((carousel) => {
      if (!carousel.items || carousel.items.length === 0) return;
      const shelf = document.createElement("div");
      shelf.className = "home-carousel-shelf carousel-shelf";

      const header = document.createElement("div");
      header.className = "home-carousel-header";

      const title = document.createElement("h3");
      title.className = "home-carousel-title";
      title.textContent = carousel.title || "In Evidenza";

      const count = document.createElement("span");
      count.className = "home-carousel-count";
      count.textContent = `${carousel.items.length} titoli`;

      header.appendChild(title);
      header.appendChild(count);
      shelf.appendChild(header);

      const row = document.createElement("div");
      row.className = "home-carousel-row horizontal-scroll";
      carousel.items.forEach((item) => {
        row.appendChild(createCardElement(item));
      });
      shelf.appendChild(row);

      fragment.appendChild(shelf);
    });

    elements.catalogCarousels.appendChild(fragment);
  }

  // Render Grid Cards
  function renderGrid(items) {
    if (elements.catalogGrid) elements.catalogGrid.classList.remove("hidden");
    elements.catalogGrid.innerHTML = "";
    elements.sectionCount.textContent = `${items.length} titoli`;

    if (!items || items.length === 0) {
      elements.emptyState.classList.remove("hidden");
      return;
    }

    elements.emptyState.classList.add("hidden");

    const fragment = document.createDocumentFragment();
    items.forEach((item) => {
      fragment.appendChild(createCardElement(item));
    });
    elements.catalogGrid.appendChild(fragment);
  }

  function appendGridItems(newItems) {
    if (!newItems || newItems.length === 0) return;
    elements.emptyState.classList.add("hidden");

    const fragment = document.createDocumentFragment();
    newItems.forEach((item) => {
      fragment.appendChild(createCardElement(item));
    });
    elements.catalogGrid.appendChild(fragment);
    elements.sectionCount.textContent = `${state.catalogItems.length} titoli`;
  }

  // Hero Banner Update
  function updateHero(item) {
    if (!item) {
      elements.heroSection.classList.add("hidden");
      return;
    }

    const backdrop = getProxiedImageUrl(item.backdrop_url) || getProxiedImageUrl(item.poster_url);
    if (!backdrop) {
      elements.heroSection.classList.add("hidden");
      return;
    }

    elements.heroBackdrop.style.backgroundImage = `url("${backdrop}")`;
    const isTv = item.type === "tv" || !!item.seasons;
    elements.heroType.textContent = isTv ? "Serie TV" : "Film";
    elements.heroRating.textContent = item.rating ? `★ ${item.rating}` : "";
    elements.heroYear.textContent = item.year ? String(item.year) : "";
    elements.heroTitle.textContent = getDisplayTitle(item);
    elements.heroDescription.textContent = item.description || "";

    elements.heroPlayBtn.onclick = () => openDetails(item);
    elements.heroInfoBtn.onclick = () => openDetails(item);

    elements.heroSection.classList.remove("hidden");
  }

  // Helper: Format human-readable display title with slug fallback
  function getDisplayTitle(item) {
    if (!item) return "Senza Titolo";
    const raw = item.title || item.name || item.original_title || item.original_name;
    if (raw && String(raw).trim() && String(raw).trim() !== "Senza Titolo") {
      return String(raw).trim();
    }
    const id = item.id || item.media_id || item.title_id;
    if (id && typeof id === "string") {
      const clean = id.replace(/^sc-/, "");
      if (clean.includes("-")) {
        const slug = clean.split("-").slice(1).join("-").replace(/_s\d+e\d+$/, "");
        const words = slug.replace(/[_-]+/g, " ").trim();
        if (words) {
          return words.split(" ").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
        }
      }
    }
    return "Senza Titolo";
  }

  // Helper: Format seconds to M:SS or H:MM:SS
  function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return "0:00";
    const s = Math.floor(seconds);
    const m = Math.floor(s / 60);
    const remS = s % 60;
    const h = Math.floor(m / 60);
    const remM = m % 60;
    const pad = (n) => String(n).padStart(2, "0");
    if (h > 0) {
      return `${h}:${pad(remM)}:${pad(remS)}`;
    }
    return `${remM}:${pad(remS)}`;
  }

  // Helper: Format certification / PEGI badge
  function formatCertification(rawCert) {
    if (!rawCert) return null;
    const cert = String(rawCert).trim().toUpperCase();
    if (!cert || cert === "ALL" || cert === "TUTTI" || cert === "NONE" || cert === "DEFAULT") return null;

    if (cert.includes("18") || cert.includes("VM18") || cert === "TV-MA" || cert === "NC-17" || cert === "R" || cert === "XXX" || cert === "ADULT") {
      return { text: "PEGI 18", class: "badge-cert-18" };
    }
    if (cert.includes("16") || cert.includes("VM16")) {
      return { text: "PEGI 16", class: "badge-cert-16" };
    }
    if (cert.includes("14") || cert.includes("VM14") || cert === "TV-14") {
      return { text: "PEGI 14", class: "badge-cert-14" };
    }
    if (cert.includes("12") || cert.includes("PG-13")) {
      return { text: "PEGI 12", class: "badge-cert-12" };
    }
    if (cert.includes("7") || cert.includes("6") || cert === "PG" || cert === "TV-PG" || cert === "TV-Y7") {
      return { text: "PEGI 7", class: "badge-cert-6" };
    }
    if (cert === "T" || cert === "0" || cert === "G" || cert === "TV-Y" || cert === "TV-G" || cert.includes("KIDS") || cert.includes("BAMBINI")) {
      return { text: "Per Tutti", class: "badge-cert-0" };
    }
    return { text: cert, class: "badge-cert" };
  }

  function updateCertBadge(rawCert) {
    if (!elements.modalCert) return;
    const certInfo = formatCertification(rawCert);
    if (certInfo) {
      elements.modalCert.textContent = certInfo.text;
      elements.modalCert.className = `badge ${certInfo.class}`;
      elements.modalCert.classList.remove("hidden");
    } else {
      elements.modalCert.classList.add("hidden");
    }
  }

  // Helper: Format last updated relative time
  function formatLastUpdated(ageSeconds, updatedAtIso = null) {
    let sec = ageSeconds;
    if ((sec === undefined || sec === null) && updatedAtIso) {
      const parsed = new Date(updatedAtIso).getTime();
      if (!isNaN(parsed)) {
        sec = Math.max(0, Math.floor((Date.now() - parsed) / 1000));
      }
    }
    if (sec === undefined || sec === null || sec < 86400) {
      return null;
    }
    const days = Math.floor(sec / 86400);
    if (days === 1) {
      return "Aggiornato ieri • Clicca per aggiornare";
    }
    if (days < 7) {
      return `Aggiornato ${days} giorni fa • Clicca per aggiornare`;
    }
    return "Aggiornato > 7 giorni fa • Clicca per aggiornare";
  }

  // All Shelves Refresh
  function refreshAllShelves() {
    loadContinueWatching();
    loadFavoritesShelf();
  }

  // Favorites Shelf & Management
  async function loadFavoritesShelf() {
    if (!elements.favoritesSection || !elements.favoritesRow) return;
    try {
      const resp = await fetch(apiUrl(`api/favorites?profile_id=${encodeURIComponent(state.activeProfileId)}`));
      if (!resp.ok) return;
      const items = await resp.json();
      state.favoritesSet = new Set((items || []).map((i) => i.id));
      renderFavoritesShelf(items || []);
    } catch (err) {
      console.warn("Could not load favorites shelf:", err);
    }
  }

  function renderFavoritesShelf(items) {
    if (!elements.favoritesSection || !elements.favoritesRow) return;
    elements.favoritesRow.innerHTML = "";

    if (!items || items.length === 0) {
      elements.favoritesSection.classList.add("hidden");
      return;
    }

    // Only show on home tab ("all") when not searching
    if (state.activeType === "all" && !state.searchQuery && !state.activeGenre) {
      elements.favoritesSection.classList.remove("hidden");
    }

    if (elements.favoritesCount) {
      elements.favoritesCount.textContent = `${items.length} preferiti`;
    }

    const fragment = document.createDocumentFragment();
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "media-card";

      const posterSrc = getProxiedImageUrl(item.poster_url) || DEFAULT_POSTER_SVG;
      const isTv = item.type === "tv" || !!item.seasons;
      const typeLabel = isTv ? "Serie TV" : "Film";
      const displayTitle = getDisplayTitle(item);

      card.innerHTML = `
        <div class="card-poster-wrap">
          <img class="card-poster" src="${posterSrc}" alt="${escapeHtml(displayTitle)}" loading="lazy" onerror="this.onerror=null;this.src='${DEFAULT_POSTER_SVG}';">
          <div class="card-badges">
            <span class="card-badge-type">${typeLabel}</span>
          </div>
        </div>
        <div class="card-info">
          <div class="card-title" title="${escapeHtml(displayTitle)}">${escapeHtml(displayTitle)}</div>
        </div>
      `;

      card.addEventListener("click", () => openDetails(item));
      fragment.appendChild(card);
    });
    elements.favoritesRow.appendChild(fragment);
  }


  // Toggle Favorite
  async function toggleFavoriteItem(item) {
    if (!item || !item.id) return;
    const isTv = item.type === "tv" || !!item.seasons;
    const displayTitle = getDisplayTitle(item);

    try {
      const payload = {
        title_id: item.id,
        media_type: isTv ? "tv" : "movie",
        title: displayTitle,
        poster_url: item.poster_url || "",
        tmdb_id: item.tmdb_id || null,
        imdb_id: item.imdb_id || null,
        profile_id: state.activeProfileId,
      };

      const resp = await fetch(apiUrl("api/favorites/toggle"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) throw new Error("Toggle favorite failed");
      const data = await resp.json();
      const isFav = !!data.favorite;

      if (isFav) {
        state.favoritesSet.add(item.id);
        showToast(`"${displayTitle}" aggiunto ai Preferiti! ❤️`, "success");
      } else {
        state.favoritesSet.delete(item.id);
        showToast(`"${displayTitle}" rimosso dai Preferiti`, "info");
      }

      // Update button visual states
      updateFavoriteButtonUI(isFav);
      loadFavoritesShelf();

      // If on favorites tab, refresh the grid
      if (state.activeType === "favorites") {
        loadCatalog();
      }
    } catch (err) {
      console.error("Toggle favorite error:", err);
      showToast("Impossibile aggiornare i preferiti", "error");
    }
  }

  function updateFavoriteButtonUI(isFavorite) {
    if (elements.btnFavoriteTrigger) {
      elements.btnFavoriteTrigger.classList.toggle("active", isFavorite);
      elements.btnFavoriteTrigger.title = isFavorite ? "Rimuovi dai Preferiti" : "Aggiungi ai Preferiti";
    }
    if (elements.heroFavoriteBtn) {
      elements.heroFavoriteBtn.classList.toggle("active", isFavorite);
      elements.heroFavoriteBtn.title = isFavorite ? "Rimuovi dai Preferiti" : "Aggiungi ai Preferiti";
    }
  }

  // Continue Watching Section
  async function loadContinueWatching() {
    try {
      const resp = await fetch(apiUrl(`api/history/continue?profile_id=${encodeURIComponent(state.activeProfileId)}`));
      if (!resp.ok) return;
      const items = await resp.json();
      renderContinueWatching(items);
    } catch (err) {
      console.warn("Could not load continue watching list:", err);
    }
  }

  function renderContinueWatching(items) {
    if (!elements.continueSection || !elements.continueRow) return;
    elements.continueRow.innerHTML = "";

    if (!items || items.length === 0) {
      elements.continueSection.classList.add("hidden");
      return;
    }

    if (state.activeType === "all" && !state.searchQuery && !state.activeGenre) {
      elements.continueSection.classList.remove("hidden");
    }

    if (elements.continueCount) {
      elements.continueCount.textContent = `${items.length} in corso`;
    }

    const fragment = document.createDocumentFragment();
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "continue-card";

      const imgSrc = getProxiedImageUrl(item.backdrop_url) || getProxiedImageUrl(item.poster_url) || "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=500&auto=format&fit=crop&q=60";
      const isTv = item.media_type === "tv";
      const displayTitle = getDisplayTitle(item);

      let epBadgeText = "";
      if (isTv) {
        if (item.is_next_episode) {
          epBadgeText = `Prossimo: S${item.season_number}E${item.episode_number}`;
        } else {
          epBadgeText = `S${item.season_number}E${item.episode_number}`;
        }
      }

      let timeText = "";
      if (item.is_next_episode) {
        timeText = "Da iniziare";
      } else if (item.remaining_seconds > 0) {
        const remMin = Math.round(item.remaining_seconds / 60);
        timeText = remMin > 0 ? `${remMin} min rimanenti` : "Quasi terminato";
      } else {
        timeText = `${Math.round(item.progress_percent)}% completato`;
      }

      card.innerHTML = `
        <div class="continue-media-wrap">
          <img class="continue-media-img" src="${imgSrc}" alt="${escapeHtml(displayTitle)}" loading="lazy" onerror="this.onerror=null;this.src='https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=500&auto=format&fit=crop&q=60';">
          <div class="continue-play-overlay">
            <div class="continue-play-icon">
              <svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            </div>
          </div>
          ${!item.is_next_episode ? `
            <div class="continue-progress-container">
              <div class="continue-progress-fill" style="width: ${Math.min(100, Math.max(0, item.progress_percent))}%;"></div>
            </div>
          ` : ""}
          <button class="continue-remove-btn" title="Rimuovi da Continua a guardare">✕</button>
        </div>
        <div class="continue-info">
          <div class="continue-title" title="${escapeHtml(displayTitle)}">${escapeHtml(displayTitle)}</div>
          <div class="continue-subtitle">
            ${epBadgeText ? `<span class="continue-ep-badge">${epBadgeText}</span>` : `<span>Film</span>`}
            <span>${timeText}</span>
          </div>
        </div>
      `;

      // Remove button click
      const removeBtn = card.querySelector(".continue-remove-btn");
      removeBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        card.style.opacity = "0.3";
        card.style.transform = "scale(0.95)";
        try {
          await fetch(apiUrl(`api/history/${encodeURIComponent(item.media_id)}?profile_id=${encodeURIComponent(state.activeProfileId)}`), { method: "DELETE" });
          loadContinueWatching();
          showToast(`"${displayTitle}" rimosso da Continua a guardare`, "info");
        } catch (err) {
          console.warn("Delete history error:", err);
        }
      });

      // Card click: open modal with pre-selected season and episode
      card.addEventListener("click", () => {
        const dummyItem = {
          id: item.media_id,
          title: displayTitle,
          type: item.media_type,
          poster_url: item.poster_url,
          backdrop_url: item.backdrop_url,
        };
        openDetails(dummyItem, item.season_number, item.episode_number);
      });

      fragment.appendChild(card);
    });
    elements.continueRow.appendChild(fragment);
  }

  // Clear Details Modal DOM state to avoid ghosting previous titles
  function resetDetailsModal() {
    if (elements.modalCastSection) elements.modalCastSection.classList.add("hidden");
    if (elements.modalCastText) elements.modalCastText.textContent = "";
    if (elements.modalWatchProviders) elements.modalWatchProviders.classList.add("hidden");
    if (elements.providersList) elements.providersList.innerHTML = "";
    if (elements.tvSeriesSection) elements.tvSeriesSection.classList.add("hidden");
    if (elements.seasonsTabs) elements.seasonsTabs.innerHTML = "";
    if (elements.episodesList) elements.episodesList.innerHTML = "";
    if (elements.sourcesSection) elements.sourcesSection.classList.add("hidden");
    if (elements.sourceSelect) elements.sourceSelect.innerHTML = "";
    if (elements.modalUpdateChip) elements.modalUpdateChip.classList.add("hidden");
    if (elements.modalGenres) elements.modalGenres.innerHTML = "";
    if (elements.modalPoster) elements.modalPoster.src = "";
    if (elements.modalBackdropImg) elements.modalBackdropImg.style.backgroundImage = "";
    if (elements.detailsModal) elements.detailsModal.scrollTop = 0;
  }

  // Open Details Modal
  async function openDetails(item, targetSeason = null, targetEpisode = null) {
    resetDetailsModal();
    const itemId = item ? (item.id || item.title_id) : null;
    const itemType = item ? (item.type || item.media_type) : null;
    const normalizedItem = item ? { ...item, id: itemId, type: itemType } : null;

    state.selectedItem = normalizedItem;
    state.selectedSeason = targetSeason || 1;
    state.selectedEpisode = null;
    state.selectedSource = null;
    state.resumeProgress = null;

    const mediaType = itemType === "tv" || !!(item && item.seasons) ? "tv" : "movie";

    const initialDisplayTitle = getDisplayTitle(item);
    // Show initial data
    elements.modalTitle.textContent = initialDisplayTitle;
    elements.modalYear.textContent = item.year || "";
    elements.modalDuration.textContent = item.duration ? `${item.duration} min` : "";
    elements.modalRating.textContent = item.rating ? `★ ${item.rating}` : "";
    updateCertBadge(item.certification);
    elements.modalTypeBadge.textContent = mediaType === "tv" ? "Serie TV" : "Film";
    elements.modalPlot.textContent = item.description || "Caricamento trama arricchita...";

    const poster = getProxiedImageUrl(item.poster_url) || "";
    elements.modalPoster.src = poster;
    const backdrop = getProxiedImageUrl(item.backdrop_url) || poster;
    elements.modalBackdropImg.style.backgroundImage = backdrop ? `url("${backdrop}")` : "";

    // Set initial favorite UI from cached Set
    const isFav = state.favoritesSet.has(itemId) || !!(item && item.is_favorite);
    updateFavoriteButtonUI(isFav);

    elements.modalGenres.innerHTML = "";
    if (item.genres) {
      item.genres.forEach((g) => {
        const tag = document.createElement("span");
        tag.className = "genre-tag";
        tag.textContent = g;
        elements.modalGenres.appendChild(tag);
      });
    }

    elements.detailsModal.classList.remove("hidden");
    document.body.style.overflow = "hidden";

    // Refresh players list lazily upon modal opening so any newly active cast devices appear
    loadPlayers();

    // Fetch full enriched details and watch progress concurrently
    try {
      const progUrl = (mediaType === "tv" && targetSeason && targetEpisode)
        ? `api/history/progress/${itemId}?season=${targetSeason}&episode=${targetEpisode}&profile_id=${encodeURIComponent(state.activeProfileId)}`
        : `api/history/progress/${itemId}?profile_id=${encodeURIComponent(state.activeProfileId)}`;
      const [detailsResp, progResp] = await Promise.all([
        fetch(apiUrl(`api/catalog/title/${mediaType}/${itemId}?profile_id=${encodeURIComponent(state.activeProfileId)}`)),
        fetch(apiUrl(progUrl)),
      ]);

      if (detailsResp.status === 403) {
        closeModal();
        showToast("Contenuto non disponibile per il profilo selezionato (restrizione d'età). 🛑", "error");
        return;
      }

      if (progResp.ok) {
        const progData = await progResp.json();
        if (progData.progress) {
          state.resumeProgress = progData.progress;
          if (mediaType === "tv" && !targetSeason && progData.progress.season_number) {
            state.selectedSeason = progData.progress.season_number;
          }
        }
      }

      if (detailsResp.ok) {
        const detailed = await detailsResp.json();
        state.selectedItem = detailed;
        const fullTitle = getDisplayTitle(detailed);
        if (fullTitle && fullTitle !== "Senza Titolo") {
          elements.modalTitle.textContent = fullTitle;
        }
        if (detailed.is_favorite !== undefined) {
          if (detailed.is_favorite) state.favoritesSet.add(itemId);
          else state.favoritesSet.delete(itemId);
          updateFavoriteButtonUI(detailed.is_favorite);
        }
        updateModalWithDetails(detailed, targetEpisode || (state.resumeProgress && state.resumeProgress.episode_number));
      } else {
        updateModalWithDetails(normalizedItem, targetEpisode);
      }
    } catch (err) {
      console.warn("Could not enrich item details:", err);
      updateModalWithDetails(normalizedItem, targetEpisode);
    }
  }

  function updateModalWithDetails(item, targetEpisode = null) {
    if (item.description) elements.modalPlot.textContent = item.description;
    if (item.backdrop_url) elements.modalBackdropImg.style.backgroundImage = `url("${getProxiedImageUrl(item.backdrop_url)}")`;
    if (item.duration) elements.modalDuration.textContent = `${item.duration} min`;
    if (item.rating) elements.modalRating.textContent = `★ ${item.rating}`;
    updateCertBadge(item.certification);

    // Cast section
    if (item.cast && item.cast.length > 0) {
      elements.modalCastText.textContent = item.cast.slice(0, 5).join(", ");
      if (item.director) elements.modalCastText.textContent += ` | Regia: ${item.director}`;
      elements.modalCastSection.classList.remove("hidden");
    } else {
      elements.modalCastSection.classList.add("hidden");
    }

    // Streaming Watch Providers
    renderWatchProviders(item.streaming_availability);

    const isTv = item.type === "tv" || (item.seasons && item.seasons.length > 0);
    if (isTv) {
      elements.tvSeriesSection.classList.remove("hidden");
      renderSeasons(item.seasons || [], state.selectedSeason, targetEpisode);
    } else {
      elements.tvSeriesSection.classList.add("hidden");
      renderSources(item.sources || []);
    }

    // Freshness Update Chip (> 24 hours check)
    if (elements.modalUpdateChip && elements.modalUpdateChipText) {
      const chipLabel = formatLastUpdated(item.age_seconds, item.updated_at);
      if (chipLabel) {
        elements.modalUpdateChipText.textContent = chipLabel;
        elements.modalUpdateChip.classList.remove("hidden");
      } else {
        elements.modalUpdateChip.classList.add("hidden");
      }
    }

    updatePlayButtonText();
  }

  // Handle manual refresh triggered by update chip
  async function handleRefreshDetailsAction() {
    const item = state.selectedItem;
    if (!item || !elements.modalUpdateChip) return;

    if (elements.modalUpdateChip.classList.contains("updating")) return;
    elements.modalUpdateChip.classList.add("updating");
    if (elements.modalUpdateChipText) {
      elements.modalUpdateChipText.textContent = "Aggiornamento in corso...";
    }

    try {
      const isTv = item.type === "tv" || (item.seasons && item.seasons.length > 0);
      const mediaType = isTv ? "tv" : "movie";
      const targetSeason = state.selectedSeason || 1;
      const targetEp = state.selectedEpisode ? state.selectedEpisode.episode_number : null;

      const refreshUrl = `api/catalog/title/${mediaType}/${item.id}?profile_id=${encodeURIComponent(state.activeProfileId)}&refresh=true`;
      const resp = await fetch(apiUrl(refreshUrl));

      if (resp.ok) {
        const fresh = await resp.json();
        state.selectedItem = fresh;

        if (isTv) {
          // Force refresh active season episodes
          const activeSeasonObj =
            (fresh.seasons || []).find((s) => s.number === targetSeason) ||
            (fresh.seasons && fresh.seasons[0]);
          if (activeSeasonObj) {
            await activateSeason(activeSeasonObj, targetEp, true);
          }
        }

        updateModalWithDetails(fresh, targetEp);
        showToast("Dati e puntate aggiornati con successo! ✓", "success");
      } else {
        showToast("Impossibile aggiornare i dati in questo momento.", "warning");
      }
    } catch (err) {
      console.warn("Error refreshing details:", err);
      showToast("Errore durante l'aggiornamento.", "error");
    } finally {
      elements.modalUpdateChip.classList.remove("updating");
      elements.modalUpdateChip.classList.add("hidden");
    }
  }

  // Render Watch Providers (Streaming Platforms)
  function renderWatchProviders(avail) {
    if (!elements.modalWatchProviders || !elements.providersList) return;

    if (!avail || (!avail.grouped_providers?.length && !avail.flatrate?.length && !avail.free?.length && !avail.ads?.length && !avail.rent?.length && !avail.buy?.length)) {
      elements.modalWatchProviders.classList.add("hidden");
      return;
    }

    if (elements.providersCountryBadge) {
      elements.providersCountryBadge.textContent = avail.country || "IT";
    }

    if (elements.justwatchLink && avail.link) {
      elements.justwatchLink.href = avail.link;
    }

    elements.providersList.innerHTML = "";
    const fragment = document.createDocumentFragment();
    let renderedCount = 0;

    // 1. Consolidated Subscription / Free Streaming Platforms (with grouping)
    if (avail.grouped_providers && avail.grouped_providers.length > 0) {
      avail.grouped_providers.forEach((gp) => {
        renderedCount++;
        const pCard = document.createElement("div");
        pCard.className = "provider-card";

        const logoSrc = gp.logo_url || (gp.logo_path ? `https://image.tmdb.org/t/p/w200${gp.logo_path}` : "");
        const logoHtml = logoSrc ? `<img class="provider-logo" src="${logoSrc}" alt="${escapeHtml(gp.provider_name)}">` : "";

        const badgesHtml = (gp.badges || [])
          .map((b) => `<span class="provider-type-tag ${b.badgeClass}">${escapeHtml(b.label)}</span>`)
          .join("");

        pCard.innerHTML = `
          ${logoHtml}
          <div class="provider-info">
            <span class="provider-name">${escapeHtml(gp.provider_name)}</span>
            <div class="provider-badges">${badgesHtml}</div>
          </div>
        `;
        fragment.appendChild(pCard);
      });
    } else {
      // Fallback if grouped_providers is not present
      const subscriptionCategories = [
        { key: "flatrate", label: "Abbonamento", badgeClass: "flatrate" },
        { key: "free", label: "Gratuito", badgeClass: "free" },
        { key: "ads", label: "Gratis con Pubblicità", badgeClass: "free" },
      ];
      subscriptionCategories.forEach((cat) => {
        const providers = avail[cat.key] || [];
        providers.forEach((p) => {
          renderedCount++;
          const pCard = document.createElement("div");
          pCard.className = "provider-card";
          const logoSrc = p.logo_url || (p.logo_path ? `https://image.tmdb.org/t/p/w200${p.logo_path}` : "");
          const logoHtml = logoSrc ? `<img class="provider-logo" src="${logoSrc}" alt="${escapeHtml(p.provider_name)}">` : "";
          pCard.innerHTML = `
            ${logoHtml}
            <div class="provider-info">
              <span class="provider-name">${escapeHtml(p.provider_name)}</span>
              <div class="provider-badges"><span class="provider-type-tag ${cat.badgeClass}">${cat.label}</span></div>
            </div>
          `;
          fragment.appendChild(pCard);
        });
      });
    }

    // 2. Separate Pay-Per-View Section (Noleggio / Acquisto)
    const ppvCategories = [
      { key: "rent", label: "Noleggio", badgeClass: "rent" },
      { key: "buy", label: "Acquisto", badgeClass: "buy" },
    ];
    ppvCategories.forEach((cat) => {
      const providers = avail[cat.key] || [];
      providers.forEach((p) => {
        renderedCount++;
        const pCard = document.createElement("div");
        pCard.className = "provider-card provider-card-ppv";
        const logoSrc = p.logo_url || (p.logo_path ? `https://image.tmdb.org/t/p/w200${p.logo_path}` : "");
        const logoHtml = logoSrc ? `<img class="provider-logo" src="${logoSrc}" alt="${escapeHtml(p.provider_name)}">` : "";
        pCard.innerHTML = `
          ${logoHtml}
          <div class="provider-info">
            <span class="provider-name">${escapeHtml(p.provider_name)}</span>
            <div class="provider-badges"><span class="provider-type-tag ${cat.badgeClass}">${cat.label}</span></div>
          </div>
        `;
        fragment.appendChild(pCard);
      });
    });

    if (renderedCount > 0) {
      elements.providersList.appendChild(fragment);
      elements.modalWatchProviders.classList.remove("hidden");
    } else {
      elements.modalWatchProviders.classList.add("hidden");
    }
  }

  // Render TV Seasons & Episodes
  function renderSeasons(seasons, targetSeason = 1, targetEpisode = null) {
    elements.seasonsTabs.innerHTML = "";
    if (!seasons || seasons.length === 0) {
      elements.episodesList.innerHTML = "<p class='empty-state-text'>Nessuna stagione trovata.</p>";
      return;
    }

    const activeSeasonObj = seasons.find((s) => s.number === targetSeason) || seasons[0];
    state.selectedSeason = activeSeasonObj.number;

    seasons.forEach((season) => {
      const btn = document.createElement("button");
      btn.className = `season-btn ${season.number === state.selectedSeason ? "active" : ""}`;
      btn.textContent = `Stagione ${season.number}`;
      btn.addEventListener("click", () => {
        elements.seasonsTabs.querySelectorAll(".season-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.selectedSeason = season.number;
        activateSeason(season);
      });
      elements.seasonsTabs.appendChild(btn);
    });

    activateSeason(activeSeasonObj, targetEpisode);
  }

  async function activateSeason(season, targetEpisode = null, forceRefresh = false) {
    if (!forceRefresh && season.episodes && season.episodes.length > 0) {
      renderEpisodes(season.episodes, targetEpisode);
      return;
    }

    elements.episodesList.innerHTML = `
      <div style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; gap: 12px; padding: 30px; color: var(--text-muted);">
        <div class="spinner" style="width: 22px; height: 22px; margin: 0; border-width: 2px;"></div>
        <span>Caricamento episodi della Stagione ${season.number}...</span>
      </div>
    `;

    try {
      const seriesId = state.selectedItem ? state.selectedItem.id : "";
      const seasonUrl = forceRefresh
        ? `api/catalog/seasons/${seriesId}/${season.number}?refresh=true`
        : `api/catalog/seasons/${seriesId}/${season.number}`;
      const resp = await fetch(apiUrl(seasonUrl));
      if (resp.ok) {
        const data = await resp.json();
        season.episodes = data.episodes || [];
        renderEpisodes(season.episodes, targetEpisode);
      } else {
        elements.episodesList.innerHTML = "<p class='empty-state-text'>Nessun episodio caricato per questa stagione.</p>";
      }
    } catch (err) {
      console.warn("Failed to fetch season episodes:", err);
      elements.episodesList.innerHTML = `<p class='empty-state-text'>Errore nel recupero degli episodi: ${escapeHtml(err.message)}</p>`;
    }
  }

  function renderEpisodes(episodes, targetEpisode = null) {
    elements.episodesList.innerHTML = "";
    if (!episodes || episodes.length === 0) {
      elements.episodesList.innerHTML = "<p>Nessun episodio caricato per questa stagione.</p>";
      return;
    }

    let defaultEp = episodes[0];
    if (targetEpisode) {
      const found = episodes.find((e) => e.episode_number === targetEpisode);
      if (found) defaultEp = found;
    }

    state.selectedEpisode = defaultEp;
    renderSources(defaultEp.sources || []);
    updatePlayButtonText();

    episodes.forEach((ep) => {
      const isSelected = ep.episode_number === state.selectedEpisode.episode_number;
      const card = document.createElement("div");
      card.className = `episode-card ${isSelected ? "active" : ""}`;

      card.innerHTML = `
        <div class="ep-number">${ep.episode_number}</div>
        <div class="ep-title">${escapeHtml(ep.title || `Episodio ${ep.episode_number}`)}</div>
      `;

      card.addEventListener("click", () => {
        elements.episodesList.querySelectorAll(".episode-card").forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        state.selectedEpisode = ep;
        renderSources(ep.sources || []);

        const seriesId = state.selectedItem ? state.selectedItem.id : "";
        if (seriesId) {
          fetch(apiUrl(`api/history/progress/${seriesId}?season=${state.selectedSeason}&episode=${ep.episode_number}&profile_id=${encodeURIComponent(state.activeProfileId)}`))
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
              state.resumeProgress = d && d.progress ? d.progress : null;
              updatePlayButtonText();
            })
            .catch(() => {
              state.resumeProgress = null;
              updatePlayButtonText();
            });
        } else {
          state.resumeProgress = null;
          updatePlayButtonText();
        }
      });

      elements.episodesList.appendChild(card);
    });
  }

  // Render Sources Dropdown
  function renderSources(sources) {
    elements.sourceSelect.innerHTML = "";
    if (!sources || sources.length === 0) {
      elements.sourcesSection.classList.add("hidden");
      state.selectedSource = null;
      return;
    }

    elements.sourcesSection.classList.remove("hidden");
    sources.forEach((s, idx) => {
      const opt = document.createElement("option");
      opt.value = idx;
      opt.textContent = `${s.provider_name} [${s.quality || "HD"}]`;
      elements.sourceSelect.appendChild(opt);
    });

    state.selectedSource = sources[0];
    elements.sourceSelect.onchange = (e) => {
      state.selectedSource = sources[e.target.value];
    };
  }

  function updatePlayButtonText() {
    const isTv = state.selectedItem && (state.selectedItem.type === "tv" || !!state.selectedItem.seasons);
    const epPrefix = isTv && state.selectedEpisode ? `S${state.selectedSeason}E${state.selectedEpisode.episode_number} ` : "";

    let hasResume = false;
    if (
      state.resumeProgress &&
      state.selectedItem &&
      String(state.resumeProgress.media_id) === String(state.selectedItem.id) &&
      state.resumeProgress.progress_seconds > 15
    ) {
      if (!isTv) {
        hasResume = true;
      } else if (
        state.selectedEpisode &&
        state.resumeProgress.season_number === state.selectedSeason &&
        state.resumeProgress.episode_number === state.selectedEpisode.episode_number
      ) {
        hasResume = true;
      }
    }
    const resumeTimeStr = hasResume ? `da ${formatTime(state.resumeProgress.progress_seconds)}` : "";

    const isCompleted = isTv && state.resumeProgress && state.resumeProgress.is_completed;
    if (isCompleted) {
      if (elements.btnRestartTrigger) {
        elements.btnRestartTrigger.classList.remove("hidden");
        elements.btnRestartTrigger.title = "Ricomincia serie da S1E1";
      }
      if (state.selectedDevice === "browser") {
        elements.btnPlayText.textContent = `✓ Serie Completata`;
      } else {
        const dev = state.mediaPlayers.find((p) => p.entity_id === state.selectedDevice);
        const name = dev ? formatDeviceName(dev.entity_id, dev.name) : "Dispositivo Cast";
        elements.btnPlayText.textContent = `✓ Serie Completata (${name})`;
      }
      return;
    }

    if (elements.btnRestartTrigger) {
      elements.btnRestartTrigger.classList.toggle("hidden", !hasResume);
    }

    if (state.selectedDevice === "browser") {
      if (hasResume) {
        elements.btnPlayText.textContent = `▶ Riprendi ${epPrefix}${resumeTimeStr}`;
      } else {
        elements.btnPlayText.textContent = `Guarda ${epPrefix}nel Browser`;
      }
    } else {
      const dev = state.mediaPlayers.find((p) => p.entity_id === state.selectedDevice);
      const name = dev ? formatDeviceName(dev.entity_id, dev.name) : "Dispositivo Cast";
      if (hasResume) {
        elements.btnPlayText.textContent = `📺 Riprendi ${epPrefix}${resumeTimeStr} su ${name}`;
      } else {
        elements.btnPlayText.textContent = `Trasmetti ${epPrefix}su ${name}`;
      }
    }
  }

  // Handle Play / Cast Trigger
  async function handlePlayAction() {
    const item = state.selectedItem;
    if (!item) return;

    const isTv = item.type === "tv" || !!item.seasons;

    // Determine target source: for TV series, ALWAYS use the active episode's sources
    let source = null;
    if (isTv && state.selectedEpisode) {
      const epSources = state.selectedEpisode.sources || [];
      if (epSources.length > 0) {
        const match = epSources.find((s) => s.id === (state.selectedSource && state.selectedSource.id));
        source = match || epSources[0];
      }
    } else {
      source = state.selectedSource;
      if (!source && item.sources && item.sources.length > 0) {
        source = item.sources[0];
      }
    }

    if (!source || !source.page_url) {
      showToast("Nessuna sorgente video disponibile per questo contenuto", "error");
      return;
    }

    const title = (isTv && state.selectedEpisode)
      ? `${item.title} - S${state.selectedSeason}E${state.selectedEpisode.episode_number}${state.selectedEpisode.title ? ": " + state.selectedEpisode.title : ""}`
      : item.title;

    if (state.selectedDevice === "browser") {
      // Local Browser Playback
      await playInBrowser(source, title);
    } else {
      // Cast playback via Home Assistant
      await castToDevice(source, title, state.selectedDevice, {
        isTv: isTv,
        season: isTv ? state.selectedSeason : null,
        episode: (isTv && state.selectedEpisode) ? state.selectedEpisode.episode_number : null,
        mediaId: item ? item.id : null,
        posterUrl: item ? (item.backdrop_url || item.poster_url || "") : "",
      });
    }
  }

  // Local Browser Playback
  async function playInBrowser(source, title) {
    showToast("Risoluzione flusso HLS in corso...", "info");
    elements.btnPlayTrigger.disabled = true;

    try {
      const currentItem = state.selectedItem;
      const isTv = currentItem && (currentItem.type === "tv" || !!currentItem.seasons);
      const mediaId = currentItem ? currentItem.id : source.media_id;
      const seasonNum = isTv ? state.selectedSeason : null;
      const epNum = (isTv && state.selectedEpisode) ? state.selectedEpisode.episode_number : null;

      let resumeSec = 0;
      if (
        state.resumeProgress &&
        String(state.resumeProgress.media_id) === String(mediaId) &&
        state.resumeProgress.progress_seconds > 15
      ) {
        if (!isTv) {
          resumeSec = state.resumeProgress.progress_seconds;
        } else if (
          state.resumeProgress.season_number === seasonNum &&
          state.resumeProgress.episode_number === epNum
        ) {
          resumeSec = state.resumeProgress.progress_seconds;
        }
      }

      const displayTitle = (currentItem ? getDisplayTitle(currentItem) : title) || "Streaming Hub";
      const sessionData = {
        media_id: mediaId,
        title: displayTitle,
        media_type: isTv ? "tv" : "movie",
        poster_url: currentItem ? (currentItem.backdrop_url || currentItem.poster_url || "") : "",
        season_number: seasonNum,
        episode_number: epNum,
        profile_id: state.activeProfileId,
        seek_seconds: resumeSec,
      };

      const payload = {
        page_url: source.page_url,
        provider_id: source.provider_id,
        media_id: source.media_id,
        quality: source.quality,
        prefer_fhd: true,
      };

      const resp = await fetch(apiUrl("api/resolve"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Risoluzione stream fallita");
      }

      const streamData = await resp.json();
      state.playbackSession = sessionData;
      closeModal();
      openPlayer(streamData.local_stream_url, displayTitle);
    } catch (err) {
      console.error("Play error:", err);
      showToast(err.message || "Impossibile avviare il video", "error");
    } finally {
      elements.btnPlayTrigger.disabled = false;
    }
  }

  // Cast to HA Device
  async function castToDevice(source, title, entityId, explicitOptions = {}) {
    const currentItem = state.selectedItem;
    const isTv = explicitOptions.isTv !== undefined ? explicitOptions.isTv : (currentItem && (currentItem.type === "tv" || !!currentItem.seasons));
    const seasonNum = explicitOptions.season !== undefined ? explicitOptions.season : (isTv ? state.selectedSeason : null);
    const epNum = explicitOptions.episode !== undefined ? explicitOptions.episode : ((isTv && state.selectedEpisode) ? state.selectedEpisode.episode_number : null);
    let mediaId = explicitOptions.mediaId || (currentItem ? currentItem.id : null);
    if (!mediaId) {
      mediaId = (isTv && source.media_id && source.media_id.includes("_s")) ? source.media_id.split("_s")[0] : source.media_id;
    }
    const effectiveTitle = (title && title !== "Senza Titolo") ? title : ((currentItem ? getDisplayTitle(currentItem) : "") || "Streaming Hub");

    let hasResume = false;
    let resumeSec = 0;
    if (
      state.resumeProgress &&
      String(state.resumeProgress.media_id) === String(mediaId) &&
      state.resumeProgress.progress_seconds > 15
    ) {
      if (!isTv) {
        hasResume = true;
        resumeSec = state.resumeProgress.progress_seconds;
      } else if (
        state.resumeProgress.season_number === seasonNum &&
        state.resumeProgress.episode_number === epNum
      ) {
        hasResume = true;
        resumeSec = state.resumeProgress.progress_seconds;
      }
    }
    const posterUrl = explicitOptions.posterUrl || (currentItem ? (currentItem.backdrop_url || currentItem.poster_url || "") : "");

    const dev = state.mediaPlayers.find((p) => p.entity_id === entityId);
    const friendlyName = formatDeviceName(entityId, dev ? dev.name : "");

    showToast(`Avvio riproduzione su ${friendlyName}...`, "info");
    elements.btnPlayTrigger.disabled = true;

    try {
      const payload = {
        entity_id: entityId,
        page_url: source.page_url,
        title: effectiveTitle,
        poster_url: posterUrl,
        provider_id: source.provider_id,
        media_id: mediaId,
        quality: source.quality,
        media_type: isTv ? "tv" : "movie",
        season_number: seasonNum,
        episode_number: epNum,
        seek_seconds: resumeSec,
        profile_id: state.activeProfileId,
      };

      const resp = await fetch(apiUrl("api/cast"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Casting fallito");
      }

      const data = await resp.json();
      const actualEntity = data.entity_id || entityId;
      const actualDev = state.mediaPlayers.find((p) => p.entity_id === actualEntity);
      const actualDevName = formatDeviceName(actualEntity, actualDev ? actualDev.name : friendlyName);

      showToast(`In riproduzione su ${actualDevName}!`, "success");

      // Show persistent Cast Control Bar BEFORE closing modal so state is preserved
      showCastBar({
        entityId: actualEntity,
        deviceName: actualDevName,
        title: effectiveTitle,
        posterUrl: posterUrl,
        isTv: isTv,
        mediaId: mediaId,
        season: seasonNum,
        episode: epNum,
        seekSeconds: resumeSec,
      });

      closeModal();
      setTimeout(loadContinueWatching, 3000);
    } catch (err) {
      console.error("Cast error:", err);
      showToast(err.message || "Errore durante il casting", "error");
    } finally {
      elements.btnPlayTrigger.disabled = false;
    }
  }

  // Video Player Logic
  function openPlayer(streamUrl, title) {
    elements.playerTitle.textContent = title;
    elements.playerModal.classList.remove("hidden");
    elements.playerSpinner.classList.remove("hidden");

    const video = elements.videoElement;
    if (video) {
      video.currentTime = 0;
    }

    const session = state.playbackSession;
    let seekSec = (session && session.seek_seconds) ? session.seek_seconds : 0;
    if (
      !seekSec &&
      state.resumeProgress &&
      session &&
      String(state.resumeProgress.media_id) === String(session.media_id) &&
      state.resumeProgress.progress_seconds > 15
    ) {
      const isTv = session.media_type === "tv";
      if (!isTv) {
        seekSec = state.resumeProgress.progress_seconds;
      } else if (
        state.resumeProgress.season_number === session.season_number &&
        state.resumeProgress.episode_number === session.episode_number
      ) {
        seekSec = state.resumeProgress.progress_seconds;
      }
    }

    if (window.Hls && Hls.isSupported()) {
      if (state.hls) {
        state.hls.destroy();
      }
      state.hls = new Hls({
        maxBufferLength: 30,
        enableWorker: true,
      });

      state.hls.loadSource(streamUrl);
      state.hls.attachMedia(video);

      state.hls.on(Hls.Events.MANIFEST_PARSED, () => {
        elements.playerSpinner.classList.add("hidden");
        video.currentTime = seekSec > 0 ? seekSec : 0;
        video.play().catch((e) => console.log("Autoplay blocked:", e));
      });

      state.hls.on(Hls.Events.ERROR, (event, data) => {
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              state.hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              state.hls.recoverMediaError();
              break;
            default:
              state.hls.destroy();
              showToast("Errore di riproduzione video HLS", "error");
              break;
          }
        }
      });
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      // Native iOS / Safari HLS
      video.src = streamUrl;
      video.addEventListener("loadedmetadata", () => {
        elements.playerSpinner.classList.add("hidden");
        video.currentTime = seekSec > 0 ? seekSec : 0;
        video.play();
      });
    } else {
      video.src = streamUrl;
      video.currentTime = seekSec > 0 ? seekSec : 0;
      video.play();
    }

    setupSubtitles(streamUrl);
    resetNextEpisodeState();
    resetSegmentsState();
    if (elements.btnSkipIntro) elements.btnSkipIntro.classList.add("hidden");
    prepareNextEpisodeAndSegments();

    video.ontimeupdate = () => reportWatchProgress(false);
    video.onpause = () => reportWatchProgress(true);
    video.onended = () => {
      reportWatchProgress(true);
      if (nextEpState.ready && !nextEpState.cancelled) {
        if (!nextEpState.triggered) {
          console.log("[StreamingHub] Video reached end: triggering countdown for next episode");
          triggerNextEpisodeCountdown();
        }
      } else {
        console.log("[StreamingHub] Video reached end: no further episodes available");
      }
    };
    video.ondurationchange = () => {
      inspectChapterTracks();
      const dur = video.duration;
      if (dur > 60 && (!segmentsState.outro || segmentsState.outro.start === undefined)) {
        const session = state.playbackSession;
        if (session && session.media_type === "tv" && session.season_number && session.episode_number) {
          prepareNextEpisodeAndSegments(dur);
        }
      }
    };
  }

  // Subtitle Management
  let activeSubtitleIndex = -1;
  let currentSubtitleTracks = [];

  function renderSubtitlesMenu(tracks) {
    if (!elements.subtitlesList) return;
    elements.subtitlesList.innerHTML = "";

    const offBtn = document.createElement("button");
    offBtn.className = `player-dropdown-item ${activeSubtitleIndex === -1 ? "active" : ""}`;
    offBtn.textContent = "Disattivati";
    offBtn.addEventListener("click", () => {
      selectSubtitleTrack(-1);
    });
    elements.subtitlesList.appendChild(offBtn);

    tracks.forEach((track, idx) => {
      const btn = document.createElement("button");
      btn.className = `player-dropdown-item ${activeSubtitleIndex === idx ? "active" : ""}`;
      btn.textContent = track.label || track.name || track.lang || `Traccia ${idx + 1}`;
      btn.addEventListener("click", () => {
        selectSubtitleTrack(idx, track);
      });
      elements.subtitlesList.appendChild(btn);
    });
  }

  function selectSubtitleTrack(index, track = null) {
    activeSubtitleIndex = index;
    if (state.hls) {
      state.hls.subtitleTrack = index;
    }
    const video = elements.videoElement;
    if (video && video.textTracks) {
      for (let i = 0; i < video.textTracks.length; i++) {
        video.textTracks[i].mode = (i === index) ? "showing" : "disabled";
      }
    }
    if (elements.subtitlesMenu) {
      elements.subtitlesMenu.classList.add("hidden");
    }
    renderSubtitlesMenu(currentSubtitleTracks);
  }

  async function setupSubtitles(streamUrl) {
    currentSubtitleTracks = [];
    activeSubtitleIndex = -1;
    renderSubtitlesMenu([]);

    if (state.hls) {
      state.hls.on(Hls.Events.SUBTITLE_TRACKS_UPDATED, (event, data) => {
        if (data.subtitleTracks && data.subtitleTracks.length > 0) {
          currentSubtitleTracks = data.subtitleTracks.map((t, idx) => ({
            id: `hls_${idx}`,
            label: t.name || t.lang || `Sottotitoli ${idx + 1}`,
            index: idx,
            isHls: true,
          }));
          renderSubtitlesMenu(currentSubtitleTracks);
        }
      });
    }

    const session = state.playbackSession;
    if (session && (session.media_id || session.title)) {
      try {
        const queryParams = new URLSearchParams();
        if (session.title) queryParams.set("query", session.title);
        if (session.season_number) queryParams.set("season", session.season_number);
        if (session.episode_number) queryParams.set("episode", session.episode_number);

        const resp = await fetch(apiUrl(`api/subtitles/search?${queryParams.toString()}`));
        if (resp.ok) {
          const externalTracks = await resp.json();
          if (Array.isArray(externalTracks) && externalTracks.length > 0) {
            const video = elements.videoElement;
            if (video) {
              const oldTracks = video.querySelectorAll("track");
              oldTracks.forEach((t) => t.remove());

              externalTracks.forEach((ext) => {
                const trackEl = document.createElement("track");
                trackEl.kind = "subtitles";
                trackEl.label = ext.label;
                trackEl.srclang = ext.language;
                trackEl.src = apiUrl(ext.url.replace(/^\//, ""));
                trackEl.addEventListener("load", () => {
                  inspectSubtitleTrackCues(trackEl.track);
                });
                video.appendChild(trackEl);
              });

              currentSubtitleTracks = externalTracks.map((t, idx) => ({
                id: t.id,
                label: t.label,
                index: idx,
                isHls: false,
              }));
              renderSubtitlesMenu(currentSubtitleTracks);
            }
          }
        }
      } catch (_) {}
    }
  }

  // Skip Segments & Next Episode Engine
  let segmentsState = {
    intro: null,
    outro: null,
    source: "none",
    subtitleLastCueTime: null,
    chapterOutroTime: null,
  };

  let nextEpState = {
    ready: false,
    triggered: false,
    cancelled: false,
    timer: null,
    countdown: 10,
    data: null,
  };

  function resetSegmentsState() {
    segmentsState = {
      intro: null,
      outro: null,
      source: "none",
      subtitleLastCueTime: null,
      chapterOutroTime: null,
    };
    if (elements.btnSkipIntro) {
      elements.btnSkipIntro.classList.add("hidden");
    }
  }

  function resetNextEpisodeState() {
    if (nextEpState.timer) {
      clearInterval(nextEpState.timer);
    }
    nextEpState = {
      ready: false,
      triggered: false,
      cancelled: false,
      timer: null,
      countdown: 10,
      data: null,
    };
    if (elements.nextEpisodeOverlay) {
      elements.nextEpisodeOverlay.classList.add("hidden");
    }
  }

  function resetCastNextEpisodeState() {
    if (elements.castNextEpisodeBanner) {
      elements.castNextEpisodeBanner.classList.add("hidden");
    }
    if (elements.castBarNextEp) {
      elements.castBarNextEp.classList.add("hidden");
    }
  }

  function inspectSubtitleTrackCues(textTrack) {
    if (!textTrack || !textTrack.cues || textTrack.cues.length === 0) return;
    const lastCue = textTrack.cues[textTrack.cues.length - 1];
    if (lastCue && typeof lastCue.endTime === "number" && lastCue.endTime > 0) {
      segmentsState.subtitleLastCueTime = lastCue.endTime;
      console.log(`[StreamingHub] Subtitle dialog ends at: ${lastCue.endTime}s`);
    }
  }

  function inspectChapterTracks() {
    const video = elements.videoElement;
    if (!video || !video.textTracks) return;
    for (let i = 0; i < video.textTracks.length; i++) {
      const track = video.textTracks[i];
      if (track.kind === "chapters" && track.cues) {
        for (let j = 0; j < track.cues.length; j++) {
          const cue = track.cues[j];
          const text = (cue.text || "").toLowerCase();
          if (/credit|outro|titoli|ending/i.test(text)) {
            segmentsState.chapterOutroTime = cue.startTime;
            console.log(`[StreamingHub] Chapter outro detected at: ${cue.startTime}s ("${cue.text}")`);
            break;
          }
        }
      }
    }
  }

  async function prepareNextEpisodeAndSegments(dur = 0) {
    const session = state.playbackSession;
    if (!session || session.media_type !== "tv" || !session.season_number || !session.episode_number) return;

    console.log(`[StreamingHub] Pre-fetching next episode & skip segments for ${session.media_id} S${session.season_number}E${session.episode_number}...`);

    try {
      const nextUrl = apiUrl(`api/catalog/next-episode/${encodeURIComponent(session.media_id)}/${session.season_number}/${session.episode_number}`);
      const durParam = dur && dur > 60 ? `?duration=${Math.round(dur)}` : "";
      const skipUrl = apiUrl(`api/catalog/skip-segments/${encodeURIComponent(session.media_id)}/${session.season_number}/${session.episode_number}${durParam}`);

      const [nextResp, skipResp] = await Promise.all([
        fetch(nextUrl).catch(() => null),
        fetch(skipUrl).catch(() => null),
      ]);

      if (nextResp && nextResp.ok) {
        const nextData = await nextResp.json();
        if (nextData && nextData.has_next && nextData.next) {
          nextEpState.data = nextData.next;
          nextEpState.ready = true;
          const ep = nextData.next.episode || {};
          console.log(`[StreamingHub] Next episode ready: S${nextData.next.season_number}:E${nextData.next.episode_number} - "${ep.title || 'Prossimo Episodio'}"`);
        } else {
          nextEpState.data = null;
          nextEpState.ready = false;
          console.log(`[StreamingHub] No next episode in catalog or end of series.`);
        }
      } else {
        nextEpState.data = null;
        nextEpState.ready = false;
      }

      if (skipResp && skipResp.ok) {
        const skipData = await skipResp.json();
        if (skipData && skipData.has_segments) {
          segmentsState.intro = skipData.intro;
          segmentsState.outro = skipData.outro;
          segmentsState.source = skipData.source;
          console.log(`[StreamingHub] SkipDB segments loaded:`, skipData);
        }
      }
    } catch (err) {
      console.warn("[StreamingHub] Error preparing next episode:", err);
    }
  }

  function calculateOutroTriggerTime(durTime) {
    if (segmentsState.outro && typeof segmentsState.outro.start === "number" && segmentsState.outro.start > 0) {
      if (segmentsState.outro.start >= durTime * 0.70 && segmentsState.outro.start < durTime - 5) {
        return segmentsState.outro.start;
      }
    }
    if (segmentsState.chapterOutroTime && segmentsState.chapterOutroTime > 0) {
      if (segmentsState.chapterOutroTime >= durTime * 0.70 && segmentsState.chapterOutroTime < durTime - 5) {
        return segmentsState.chapterOutroTime;
      }
    }
    // Subtitles should not be used as an outro trigger: dialogue often concludes minutes before credits.
    // Fallback: Trigger strictly during the final credits in the last 30-35 seconds of the video.
    if (durTime > 60) {
      return Math.max(durTime - 35, durTime * 0.98);
    }
    return durTime;
  }

  function checkSkipIntroTrigger(curTime) {
    if (!elements.btnSkipIntro) return;
    if (segmentsState.intro && typeof segmentsState.intro.start === "number" && typeof segmentsState.intro.end === "number") {
      const inIntro = curTime >= segmentsState.intro.start && curTime < segmentsState.intro.end;
      if (inIntro) {
        elements.btnSkipIntro.classList.remove("hidden");
      } else {
        elements.btnSkipIntro.classList.add("hidden");
      }
    } else {
      elements.btnSkipIntro.classList.add("hidden");
    }
  }

  function skipIntroAction() {
    const video = elements.videoElement;
    if (video && segmentsState.intro && segmentsState.intro.end) {
      video.currentTime = segmentsState.intro.end + 0.5;
      if (elements.btnSkipIntro) elements.btnSkipIntro.classList.add("hidden");
      showToast("Intro saltata ⏭", "info");
    }
  }

  function checkNextEpisodeTrigger(curTime, durTime) {
    checkSkipIntroTrigger(curTime);

    const session = state.playbackSession;
    if (!session || session.media_type !== "tv" || !session.season_number || !session.episode_number) return;
    if (!nextEpState.ready || nextEpState.triggered || nextEpState.cancelled) return;
    if (durTime <= 30) return;

    const outroTriggerTime = calculateOutroTriggerTime(durTime);
    if (curTime >= outroTriggerTime) {
      console.log(`[StreamingHub] Triggering next episode at ${curTime}s (outro: ${outroTriggerTime}s, dur: ${durTime}s)`);
      triggerNextEpisodeCountdown();
    }
  }

  function triggerNextEpisodeCountdown() {
    nextEpState.triggered = true;
    const nextData = nextEpState.data;
    if (!nextData || !nextData.episode) return;

    const nextEp = nextData.episode;
    if (elements.nextEpTitle) {
      elements.nextEpTitle.textContent = `S${nextData.season_number}:E${nextData.episode_number} - ${nextEp.title || "Prossimo Episodio"}`;
    }
    if (elements.nextEpDesc) {
      elements.nextEpDesc.textContent = nextEp.description || "";
    }
    if (elements.nextEpisodeOverlay) {
      elements.nextEpisodeOverlay.classList.remove("hidden");
    }

    const fullEl = document.fullscreenElement || document.webkitFullscreenElement;
    if (fullEl === elements.videoElement && elements.playerModal) {
      if (elements.playerModal.requestFullscreen) {
        elements.playerModal.requestFullscreen().catch(() => {});
      }
    }

    nextEpState.countdown = 10;
    if (elements.nextEpCountdown) {
      elements.nextEpCountdown.textContent = "10";
    }

    if (nextEpState.timer) clearInterval(nextEpState.timer);
    nextEpState.timer = setInterval(() => {
      nextEpState.countdown -= 1;
      if (elements.nextEpCountdown) {
        elements.nextEpCountdown.textContent = String(nextEpState.countdown);
      }
      if (nextEpState.countdown <= 0) {
        clearInterval(nextEpState.timer);
        playPendingNextEpisode();
      }
    }, 1000);
  }

  function cancelPendingNextEpisode() {
    if (nextEpState.timer) clearInterval(nextEpState.timer);
    nextEpState.cancelled = true;
    if (elements.nextEpisodeOverlay) {
      elements.nextEpisodeOverlay.classList.add("hidden");
    }
    showToast("Riproduzione automatica annullata", "info");
  }

  async function playPendingNextEpisode() {
    if (nextEpState.timer) clearInterval(nextEpState.timer);
    if (!nextEpState.data) return;

    const nextData = nextEpState.data;
    const nextEp = nextData.episode;
    resetNextEpisodeState();
    state.resumeProgress = null;

    if (!nextEp.sources || nextEp.sources.length === 0) {
      showToast("Nessuna sorgente disponibile per il prossimo episodio", "warning");
      return;
    }

    const firstSource = nextEp.sources[0];
    try {
      showLoading(true);
      const resolveResp = await fetch(apiUrl("api/resolve"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          page_url: firstSource.page_url,
          provider_id: firstSource.provider_id,
          media_id: firstSource.media_id,
          quality: firstSource.quality,
        }),
      });

      if (!resolveResp.ok) {
        throw new Error("Risoluzione prossimo episodio fallita");
      }

      const streamData = await resolveResp.json();
      state.playbackSession = {
        media_id: nextData.series_id,
        title: `${state.selectedItem ? state.selectedItem.title : "Serie TV"} - S${nextData.season_number}E${nextData.episode_number}`,
        media_type: "tv",
        poster_url: nextEp.poster_url || (state.selectedItem ? state.selectedItem.poster_url : null),
        season_number: nextData.season_number,
        episode_number: nextData.episode_number,
        profile_id: state.activeProfileId,
        seek_seconds: 0,
      };

      openPlayer(streamData.local_stream_url, state.playbackSession.title);
    } catch (err) {
      showToast(err.message || "Errore riproduzione prossimo episodio", "error");
    } finally {
      showLoading(false);
    }
  }

  // Cast Next Episode Functions (Server-Synchronized)
  function updateCastNextEpisodeBanner(nextEpState) {
    if (!elements.castNextEpisodeBanner) return;
    if (nextEpState && nextEpState.countdown_active && nextEpState.has_next) {
      if (elements.castNextEpTitle) {
        elements.castNextEpTitle.textContent = nextEpState.title || "Passaggio al prossimo episodio...";
      }
      if (elements.castNextCountdown) {
        elements.castNextCountdown.textContent = String(nextEpState.countdown_remaining || 0);
      }
      elements.castNextEpisodeBanner.classList.remove("hidden");
    } else {
      elements.castNextEpisodeBanner.classList.add("hidden");
    }
  }

  async function triggerNextEpisodeAction(action) {
    const entityId = state.castSession ? state.castSession.entityId : null;
    try {
      const resp = await fetch(apiUrl("api/cast/next-episode/action"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          entity_id: entityId,
          action: action,
        }),
      });
      if (resp.ok) {
        if (action === "play_now") {
          showToast("Avvio prossimo episodio...", "info");
        } else if (action === "cancel") {
          showToast("Riproduzione automatica annullata", "info");
        }
        if (elements.castNextEpisodeBanner) {
          elements.castNextEpisodeBanner.classList.add("hidden");
        }
      }
    } catch (err) {
      console.warn("Failed sending next episode action:", err);
    }
  }

  let lastProgressReportTime = 0;
  async function reportWatchProgress(force = false) {
    const video = elements.videoElement;
    const session = state.playbackSession;
    if (!video || !session || !video.currentTime) return;

    const curTime = Number.isFinite(video.currentTime) ? video.currentTime : 0;
    const durTime = Number.isFinite(video.duration) ? video.duration : 0;

    checkNextEpisodeTrigger(curTime, durTime);

    const now = Date.now();
    if (!force && now - lastProgressReportTime < 5000) return;
    lastProgressReportTime = now;

    const payload = {
      media_id: session.media_id,
      title: session.title,
      media_type: session.media_type,
      poster_url: session.poster_url,
      season_number: session.season_number,
      episode_number: session.episode_number,
      progress_seconds: curTime,
      duration_seconds: durTime,
      profile_id: session.profile_id || state.activeProfileId,
    };

    try {
      await fetch(apiUrl("api/history"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: true,
      });
    } catch (_) {}
  }

  function toggleFullscreen() {
    const isFull = !!(document.fullscreenElement || document.webkitFullscreenElement);
    if (!isFull) {
      const container = elements.playerModal || elements.videoContainer || elements.videoElement;
      if (container && container.requestFullscreen) {
        container.requestFullscreen().catch(() => {
          if (elements.videoElement && elements.videoElement.webkitEnterFullscreen) {
            elements.videoElement.webkitEnterFullscreen();
          }
        });
      } else if (container && container.webkitRequestFullscreen) {
        container.webkitRequestFullscreen();
      } else if (elements.videoElement && elements.videoElement.webkitEnterFullscreen) {
        elements.videoElement.webkitEnterFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
    }
  }

  async function closePlayer() {
    await reportWatchProgress(true);
    resetNextEpisodeState();
    resetSegmentsState();
    if (elements.btnSkipIntro) elements.btnSkipIntro.classList.add("hidden");
    state.playbackSession = null;
    state.resumeProgress = null;
    if (elements.videoElement) {
      elements.videoElement.currentTime = 0;
      elements.videoElement.ontimeupdate = null;
      elements.videoElement.onpause = null;
      elements.videoElement.onended = null;
      elements.videoElement.ondurationchange = null;
    }
    if (document.fullscreenElement || document.webkitFullscreenElement) {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
    }
    if (state.hls) {
      state.hls.destroy();
      state.hls = null;
    }
    elements.videoElement.pause();
    elements.videoElement.removeAttribute("src");
    elements.videoElement.load();
    elements.playerModal.classList.add("hidden");
    loadContinueWatching();
  }

  function closeModal() {
    elements.detailsModal.classList.add("hidden");
    document.body.style.overflow = "";
    state.selectedItem = null;
    state.resumeProgress = null;
  }

  function showLoading(show) {
    elements.loadingSpinner.classList.toggle("hidden", !show);
  }

  // Toast Notification
  function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(40px)";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // ==========================================
  // Cast Playback Bar & Control Logic
  // ==========================================

  function showCastBar(initData) {
    if (!elements.castBar) return;

    state.castSession = {
      active: true,
      entityId: initData.entityId,
      deviceName: initData.deviceName || initData.entityId,
      title: initData.title || "In riproduzione",
      posterUrl: initData.posterUrl || "",
      isTv: !!initData.isTv,
      season: initData.season,
      episode: initData.episode,
      state: "playing",
      position: initData.seekSeconds || 0,
      duration: 0,
      volume: 1,
      muted: false,
      isSeeking: false,
      pollTimer: null,
      localTimer: null,
      idleCount: 0,
    };

    if (elements.castBarTitle) elements.castBarTitle.textContent = state.castSession.title;
    if (elements.castBarDevice) elements.castBarDevice.textContent = state.castSession.deviceName;
    if (elements.castBarPoster) {
      if (state.castSession.posterUrl) {
        elements.castBarPoster.src = state.castSession.posterUrl;
        elements.castBarPoster.classList.remove("hidden");
      } else {
        elements.castBarPoster.src = "";
      }
    }

    if (elements.castBarBadge) {
      if (state.castSession.isTv && state.castSession.season && state.castSession.episode) {
        elements.castBarBadge.textContent = `S${state.castSession.season}:E${state.castSession.episode}`;
        elements.castBarBadge.classList.remove("hidden");
      } else {
        elements.castBarBadge.classList.add("hidden");
      }
    }

    updateCastStatusUI("playing");
    renderCastProgressUI();

    elements.castBar.classList.remove("hidden");
    document.body.classList.add("cast-active");

    resetCastNextEpisodeState();
    startCastPolling(initData.entityId);
  }

  function hideCastBar() {
    stopCastPolling();
    resetCastNextEpisodeState();
    if (elements.castBar) {
      elements.castBar.classList.add("hidden");
    }
    document.body.classList.remove("cast-active");
    state.castSession.active = false;
    loadContinueWatching();
  }

  function updateCastStatusUI(playbackState) {
    const isPlaying = playbackState === "playing";
    const isBuffering = playbackState === "buffering";

    if (elements.castIconPlay && elements.castIconPause) {
      if (isPlaying) {
        elements.castIconPlay.classList.add("hidden");
        elements.castIconPause.classList.remove("hidden");
      } else {
        elements.castIconPlay.classList.remove("hidden");
        elements.castIconPause.classList.add("hidden");
      }
    }

    if (elements.castBarStatusDot) {
      elements.castBarStatusDot.className = "cast-bar-status-dot";
      if (!isPlaying && !isBuffering) {
        elements.castBarStatusDot.classList.add("paused");
      } else if (isBuffering) {
        elements.castBarStatusDot.classList.add("buffering");
      }
    }

    if (elements.castBarStatus) {
      if (isPlaying) {
        elements.castBarStatus.textContent = "In riproduzione";
      } else if (isBuffering) {
        elements.castBarStatus.textContent = "Caricamento...";
      } else if (playbackState === "paused") {
        elements.castBarStatus.textContent = "In pausa";
      } else {
        elements.castBarStatus.textContent = playbackState;
      }
    }
  }

  function startCastPolling(entityId) {
    stopCastPolling();

    // Fast local timer every 1s for smooth progress bar progression
    state.castSession.localTimer = setInterval(() => {
      if (state.castSession.active && state.castSession.state === "playing" && !state.castSession.isSeeking) {
        state.castSession.position += 1;
        if (state.castSession.duration > 0 && state.castSession.position > state.castSession.duration) {
          state.castSession.position = state.castSession.duration;
        }
        renderCastProgressUI();
      }
    }, 1000);

    // Initial immediate fetch
    pollCastStatus(entityId);

    // Periodic HA poll every 3 seconds
    state.castSession.pollTimer = setInterval(() => {
      pollCastStatus(entityId);
    }, 3000);
  }

  function stopCastPolling() {
    if (state.castSession.pollTimer) {
      clearInterval(state.castSession.pollTimer);
      state.castSession.pollTimer = null;
    }
    if (state.castSession.localTimer) {
      clearInterval(state.castSession.localTimer);
      state.castSession.localTimer = null;
    }
  }

  async function pollCastStatus(entityId) {
    try {
      const url = apiUrl(`api/cast/status?entity_id=${encodeURIComponent(entityId)}`);
      const resp = await fetch(url);
      if (!resp.ok) return;

      const data = await resp.json();
      if (!data) return;

      if (!data.active && data.state && ["off", "idle", "standby"].includes(data.state)) {
        if (data.next_episode && data.next_episode.countdown_active) {
          state.castSession.idleCount = 0;
        } else {
          state.castSession.idleCount = (state.castSession.idleCount || 0) + 1;
          if (state.castSession.idleCount >= 3) {
            hideCastBar();
            return;
          }
        }
      } else if (data.active) {
        state.castSession.idleCount = 0;
      }

      state.castSession.state = data.state || "playing";
      if (!state.castSession.isSeeking) {
        const sPos = Number(data.media_position) || 0;
        if (sPos > 0) {
          if (Math.abs(sPos - (state.castSession.position || 0)) > 1.5) {
            state.castSession.position = sPos;
          }
        }
      }
      if (data.media_duration && data.media_duration > 0) {
        state.castSession.duration = data.media_duration;
      }
      state.castSession.volume = data.volume_level !== undefined ? data.volume_level : 1;
      state.castSession.muted = !!data.is_volume_muted;

      if (data.next_episode) {
        updateCastNextEpisodeBanner(data.next_episode);
      } else {
        updateCastNextEpisodeBanner(null);
      }

      if (data.title && elements.castBarTitle) {
        elements.castBarTitle.textContent = data.title;
      }
      if (data.season_number && data.episode_number && elements.castBarBadge) {
        state.castSession.season = data.season_number;
        state.castSession.episode = data.episode_number;
        elements.castBarBadge.textContent = `S${data.season_number}:E${data.episode_number}`;
        elements.castBarBadge.classList.remove("hidden");
      }
      if (data.device_name && elements.castBarDevice) {
        elements.castBarDevice.textContent = data.device_name;
      }
      if (data.poster_url && elements.castBarPoster && !elements.castBarPoster.src) {
        elements.castBarPoster.src = getProxiedImageUrl(data.poster_url);
      }

      updateCastStatusUI(state.castSession.state);
      renderCastProgressUI();
      renderCastVolumeUI();
    } catch (err) {
      console.debug("Cast poll error:", err);
    }
  }

  function renderCastProgressUI() {
    const curSec = Math.max(0, Math.floor(state.castSession.position || 0));
    const durSec = Math.max(0, Math.floor(state.castSession.duration || 0));

    if (elements.castBarCurTime) {
      elements.castBarCurTime.textContent = formatTime(curSec);
    }
    if (elements.castBarTotalTime) {
      elements.castBarTotalTime.textContent = durSec > 0 ? formatTime(durSec) : "--:--";
    }

    if (durSec > 0 && !state.castSession.isSeeking) {
      const pct = Math.min(100, Math.max(0, (curSec / durSec) * 100));
      if (elements.castBarSliderFill) {
        elements.castBarSliderFill.style.width = `${pct}%`;
      }
      if (elements.castBarSlider) {
        elements.castBarSlider.value = Math.round(pct * 10);
      }
    }
  }

  function renderCastVolumeUI() {
    if (elements.castBarVolSlider) {
      elements.castBarVolSlider.value = Math.round((state.castSession.volume || 1) * 100);
    }
    if (elements.castIconVol && elements.castIconVolMute) {
      if (state.castSession.muted || state.castSession.volume === 0) {
        elements.castIconVol.classList.add("hidden");
        elements.castIconVolMute.classList.remove("hidden");
      } else {
        elements.castIconVol.classList.remove("hidden");
        elements.castIconVolMute.classList.add("hidden");
      }
    }
  }

  async function sendCastControl(command, value = null) {
    if (!state.castSession.entityId) return false;
    try {
      const resp = await fetch(apiUrl("api/cast/control"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          entity_id: state.castSession.entityId,
          command: command,
          value: value,
        }),
      });
      return resp.ok;
    } catch (err) {
      console.warn(`Failed to send cast control ${command}:`, err);
      return false;
    }
  }

  async function toggleCastPlayPause() {
    const isCurrentlyPlaying = state.castSession.state === "playing";
    const newState = isCurrentlyPlaying ? "paused" : "playing";
    state.castSession.state = newState;
    updateCastStatusUI(newState);
    await sendCastControl("play_pause");
  }

  async function seekCastRelative(deltaSeconds) {
    const durSec = state.castSession.duration || 0;
    let target = (state.castSession.position || 0) + deltaSeconds;
    if (target < 0) target = 0;
    if (durSec > 0 && target > durSec) target = durSec;

    state.castSession.position = target;
    renderCastProgressUI();
    await sendCastControl("seek", target);
  }

  function handleCastSliderInput(e) {
    state.castSession.isSeeking = true;
    const durSec = state.castSession.duration || 0;
    const pct = parseInt(e.target.value, 10) / 10;
    if (elements.castBarSliderFill) {
      elements.castBarSliderFill.style.width = `${pct}%`;
    }
    if (durSec > 0 && elements.castBarCurTime) {
      const previewSec = Math.round((pct / 100) * durSec);
      elements.castBarCurTime.textContent = formatTime(previewSec);
    }
  }

  async function handleCastSliderChange(e) {
    const durSec = state.castSession.duration || 0;
    const pct = parseInt(e.target.value, 10) / 10;
    if (durSec > 0) {
      const targetSec = Math.round((pct / 100) * durSec);
      state.castSession.position = targetSec;
      await sendCastControl("seek", targetSec);
    }
    state.castSession.isSeeking = false;
  }

  async function toggleCastMute() {
    state.castSession.muted = !state.castSession.muted;
    renderCastVolumeUI();
    await sendCastControl("volume_mute", state.castSession.muted);
  }

  async function handleCastVolumeChange(e) {
    const vol = parseInt(e.target.value, 10) / 100;
    state.castSession.volume = vol;
    state.castSession.muted = vol === 0;
    renderCastVolumeUI();
    await sendCastControl("volume_set", vol);
  }

  async function stopCastPlayback() {
    showToast("Interruzione trasmissione Cast...", "info");
    await sendCastControl("stop");
    hideCastBar();
    showToast("Riproduzione interrotta", "success");
  }

  async function checkActiveCastSession() {
    try {
      const resp = await fetch(apiUrl("api/cast/status"));
      if (!resp.ok) return;
      const data = await resp.json();
      if (data && data.active && data.entity_id) {
        showCastBar({
          entityId: data.entity_id,
          deviceName: formatDeviceName(data.entity_id, data.device_name),
          title: data.title,
          posterUrl: data.poster_url,
          isTv: data.media_type === "tv",
          season: data.season_number,
          episode: data.episode_number,
          seekSeconds: data.media_position,
        });
      }
    } catch (err) {
      console.debug("Could not restore cast session:", err);
    }
  }

  // Handle Mobile App Standby / Background wake up with throttle
  let lastResumeTime = 0;
  function handleAppResume() {
    const now = Date.now();
    // Throttle: ignore resumes fired less than 15 seconds apart to avoid flooding HA / browser
    if (now - lastResumeTime < 15000) {
      return;
    }
    lastResumeTime = now;

    console.debug("[StreamingHub] Resuming from background/standby");
    // Clear stuck loading states or disabled buttons
    if (elements.btnPlayTrigger) {
      elements.btnPlayTrigger.disabled = false;
    }
    showLoading(false);

    // Refresh core states
    loadPlayers();
    refreshAllShelves();

    // Check or resume active cast polling
    if (state.castSession && state.castSession.active && state.castSession.entityId) {
      startCastPolling(state.castSession.entityId);
    } else {
      checkActiveCastSession();
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      handleAppResume();
    } else if (document.visibilityState === "hidden") {
      if (state.playbackSession && elements.videoElement && !elements.videoElement.paused) {
        reportWatchProgress(true);
      }
    }
  });

  window.addEventListener("beforeunload", () => {
    if (state.playbackSession && elements.videoElement) {
      reportWatchProgress(true);
    }
  });

  window.addEventListener("pageshow", () => {
    handleAppResume();
  });

  // Start app on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
