/**
 * Photo Archive — Vanilla JS
 * Lazy loading, lightbox, search/filter, theme toggle
 * No external dependencies.
 */
(function () {
  "use strict";

  // ===== Lazy Loading (IntersectionObserver) =====
  function initLazyLoad() {
    var images = document.querySelectorAll("img[data-src]");
    if (!images.length) return;

    if ("IntersectionObserver" in window) {
      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              var img = entry.target;
              img.src = img.getAttribute("data-src");
              img.removeAttribute("data-src");
              observer.unobserve(img);
            }
          });
        },
        { rootMargin: "200px" }
      );
      images.forEach(function (img) {
        observer.observe(img);
      });
    } else {
      // Fallback: load all
      images.forEach(function (img) {
        img.src = img.getAttribute("data-src");
        img.removeAttribute("data-src");
      });
    }
  }

  // ===== Theme Toggle =====
  function initTheme() {
    var btn = document.getElementById("btn-theme");
    if (!btn) return;

    var stored = localStorage.getItem("pa-theme");
    if (stored) {
      document.documentElement.setAttribute("data-theme", stored);
    }

    btn.addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme");
      var next;
      if (current === "dark") {
        next = "light";
      } else if (current === "light") {
        next = "dark";
      } else {
        // Auto — toggle to opposite of system preference
        var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        next = prefersDark ? "light" : "dark";
      }
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("pa-theme", next);
    });
  }

  // ===== Search Drawer =====
  function initSearch() {
    var btnOpen = document.getElementById("btn-search");
    var btnClose = document.getElementById("btn-close-search");
    var drawer = document.getElementById("search-drawer");
    var overlay = drawer ? drawer.querySelector(".drawer-overlay") : null;
    var searchInput = document.getElementById("search-input");
    var filterChipsEl = document.getElementById("filter-chips");
    var activeFiltersEl = document.getElementById("active-filters");

    if (!btnOpen || !drawer) return;

    function openDrawer() {
      drawer.classList.remove("hidden");
      if (searchInput) searchInput.focus();
    }
    function closeDrawer() {
      drawer.classList.add("hidden");
    }

    btnOpen.addEventListener("click", openDrawer);
    if (btnClose) btnClose.addEventListener("click", closeDrawer);
    if (overlay) overlay.addEventListener("click", closeDrawer);

    // Collect unique filter values from cards
    var cards = document.querySelectorAll(".photo-card");
    var filterSets = { camera: {}, lens: {}, iso: {}, aperture: {}, focal: {} };

    cards.forEach(function (card) {
      Object.keys(filterSets).forEach(function (key) {
        var val = card.getAttribute("data-" + key);
        if (val && val.trim()) {
          filterSets[key][val.trim()] = (filterSets[key][val.trim()] || 0) + 1;
        }
      });
    });

    // Build filter chips
    if (filterChipsEl) {
      Object.keys(filterSets).forEach(function (key) {
        var values = Object.keys(filterSets[key]).sort();
        if (!values.length) return;
        values.slice(0, 20).forEach(function (val) {
          var chip = document.createElement("button");
          chip.className = "filter-chip";
          chip.setAttribute("data-filter-key", key);
          chip.setAttribute("data-filter-val", val);
          chip.textContent = val;
          chip.title = key;
          filterChipsEl.appendChild(chip);
        });
      });
    }

    // Active filters state
    var activeFilters = {};

    function applyFilters() {
      var query = searchInput ? searchInput.value.toLowerCase().trim() : "";
      var hasFilters = Object.keys(activeFilters).length > 0 || query.length > 0;

      cards.forEach(function (card) {
        var show = true;

        // Text search
        if (query) {
          var text = (
            (card.getAttribute("data-camera") || "") +
            " " +
            (card.getAttribute("data-lens") || "") +
            " " +
            (card.getAttribute("data-date") || "") +
            " " +
            (card.querySelector(".photo-date") ? card.querySelector(".photo-date").textContent : "")
          ).toLowerCase();
          if (text.indexOf(query) === -1) show = false;
        }

        // Chip filters
        Object.keys(activeFilters).forEach(function (fkey) {
          var cardVal = card.getAttribute("data-" + fkey) || "";
          if (cardVal.trim() !== activeFilters[fkey]) {
            show = false;
          }
        });

        card.style.display = show ? "" : "none";
      });

      // Show active filter info
      if (activeFiltersEl) {
        var parts = [];
        Object.keys(activeFilters).forEach(function (k) {
          parts.push(k + ": " + activeFilters[k]);
        });
        if (query) parts.unshift("検索: " + query);
        activeFiltersEl.textContent = parts.length ? parts.join(" / ") : "";
      }
    }

    // Chip click
    if (filterChipsEl) {
      filterChipsEl.addEventListener("click", function (e) {
        var chip = e.target.closest(".filter-chip");
        if (!chip) return;
        var key = chip.getAttribute("data-filter-key");
        var val = chip.getAttribute("data-filter-val");

        if (chip.classList.contains("active")) {
          chip.classList.remove("active");
          delete activeFilters[key];
        } else {
          // Deactivate other chips in same group
          filterChipsEl
            .querySelectorAll('.filter-chip[data-filter-key="' + key + '"]')
            .forEach(function (c) {
              c.classList.remove("active");
            });
          chip.classList.add("active");
          activeFilters[key] = val;
        }
        applyFilters();
      });
    }

    // Text search
    if (searchInput) {
      var debounce;
      searchInput.addEventListener("input", function () {
        clearTimeout(debounce);
        debounce = setTimeout(applyFilters, 200);
      });
    }
  }

  // ===== Lightbox =====
  function initLightbox() {
    var lightbox = document.getElementById("lightbox");
    if (!lightbox) return;

    var lbImg = lightbox.querySelector(".lb-img");
    var lbDate = lightbox.querySelector(".lb-date");
    var lbCamera = lightbox.querySelector(".lb-camera");
    var lbSettings = lightbox.querySelector(".lb-settings");
    var btnClose = lightbox.querySelector(".lb-close");
    var btnPrev = lightbox.querySelector(".lb-prev");
    var btnNext = lightbox.querySelector(".lb-next");
    var lbOverlay = lightbox.querySelector(".lb-overlay");

    var allLinks = [];
    var currentIndex = 0;

    function collectLinks() {
      allLinks = Array.from(document.querySelectorAll(".photo-link"));
    }

    function show(index) {
      if (index < 0 || index >= allLinks.length) return;
      currentIndex = index;
      var link = allLinks[index];
      var viewSrc = link.getAttribute("data-view");
      var card = link.closest(".photo-card");

      lbImg.src = viewSrc || "";
      if (lbDate && card) {
        var dateEl = card.querySelector(".photo-date");
        lbDate.textContent = dateEl ? dateEl.textContent : "";
      }
      if (lbCamera && card) {
        lbCamera.textContent = card.getAttribute("data-camera") || "";
      }
      if (lbSettings && card) {
        var parts = [];
        var f = card.getAttribute("data-aperture");
        var s = card.getAttribute("data-focal");
        var iso = card.getAttribute("data-iso");
        if (f) parts.push(f);
        if (s) parts.push(s);
        if (iso) parts.push("ISO " + iso);
        lbSettings.textContent = parts.join(" \u00b7 ");
      }

      lightbox.classList.remove("hidden");
      document.body.style.overflow = "hidden";
    }

    function hide() {
      lightbox.classList.add("hidden");
      document.body.style.overflow = "";
      lbImg.src = "";
    }

    function prev() {
      // Skip hidden cards
      var i = currentIndex - 1;
      while (i >= 0) {
        var card = allLinks[i].closest(".photo-card");
        if (!card || card.style.display !== "none") break;
        i--;
      }
      if (i >= 0) show(i);
    }

    function next() {
      var i = currentIndex + 1;
      while (i < allLinks.length) {
        var card = allLinks[i].closest(".photo-card");
        if (!card || card.style.display !== "none") break;
        i++;
      }
      if (i < allLinks.length) show(i);
    }

    // Event delegation on photo grid
    document.addEventListener("click", function (e) {
      var link = e.target.closest(".photo-link");
      if (link) {
        e.preventDefault();
        collectLinks();
        var idx = allLinks.indexOf(link);
        if (idx >= 0) show(idx);
      }
    });

    if (btnClose) btnClose.addEventListener("click", hide);
    if (lbOverlay) lbOverlay.addEventListener("click", hide);
    if (btnPrev) btnPrev.addEventListener("click", prev);
    if (btnNext) btnNext.addEventListener("click", next);

    // Keyboard
    document.addEventListener("keydown", function (e) {
      if (lightbox.classList.contains("hidden")) return;
      if (e.key === "Escape") hide();
      if (e.key === "ArrowLeft") prev();
      if (e.key === "ArrowRight") next();
    });
  }

  // ===== Init =====
  document.addEventListener("DOMContentLoaded", function () {
    initLazyLoad();
    initTheme();
    initSearch();
    initLightbox();
  });
})();
