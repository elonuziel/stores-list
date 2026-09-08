/**
 * Behatsdaa Multi-Card Participating Stores Web Application
 */

(function () {
  'use strict';

  // Application State
  let storeData = null;
  let allStores = [];
  let availableCards = [];
  let currentCard = 'all';
  let currentCategory = 'all';
  let searchQuery = '';
  let currentSort = 'discount-desc';
  let currentView = localStorage.getItem('behatsdaa_view') || 'grid';

  // DOM Elements
  const searchInput = document.getElementById('search-input');
  const clearSearchBtn = document.getElementById('clear-search-btn');
  const cardFilterSelect = document.getElementById('card-filter-select');
  const sortSelect = document.getElementById('sort-select');
  const categoryChipsContainer = document.getElementById('category-chips-container');
  const matchingCountEl = document.getElementById('matching-count');
  const totalCountEl = document.getElementById('total-count');
  const activeFilterBadge = document.getElementById('active-filter-badge');
  const activeFilterText = document.getElementById('active-filter-text');
  const resetFiltersBtn = document.getElementById('reset-filters-btn');
  const lastUpdatedDateEl = document.getElementById('last-updated-date');

  const cardsView = document.getElementById('cards-view');
  const tableView = document.getElementById('table-view');
  const tableTbody = document.getElementById('table-tbody');
  const noResultsEl = document.getElementById('no-results');
  const clearFiltersBtn = document.getElementById('clear-filters-btn');

  const viewGridBtn = document.getElementById('view-grid-btn');
  const viewTableBtn = document.getElementById('view-table-btn');
  const themeToggleBtn = document.getElementById('theme-toggle-btn');

  // Modal Elements
  const storeModal = document.getElementById('store-modal');
  const modalCloseBtn = document.getElementById('modal-close-btn');
  const modalDismissBtn = document.getElementById('modal-dismiss-btn');
  const modalLogo = document.getElementById('modal-logo');
  const modalLogoWrapper = document.getElementById('modal-logo-wrapper');
  const modalCategory = document.getElementById('modal-category');
  const modalTitle = document.getElementById('modal-title');
  const modalWebsiteLink = document.getElementById('modal-website-link');
  const modalCardsList = document.getElementById('modal-cards-list');
  const modalConditions = document.getElementById('modal-conditions');

  // Initialize theme
  function initTheme() {
    const savedTheme = localStorage.getItem('behatsdaa_theme');
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }

  // Toggle Dark/Light Theme
  function toggleTheme() {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('behatsdaa_theme', isDark ? 'dark' : 'light');
  }

  // Hebrew Text Normalizer for robust search
  function normalizeHebrew(text) {
    if (!text) return '';
    return String(text)
      .toLowerCase()
      // Remove Hebrew diacritics / niqqud
      .replace(/[\u0591-\u05C7]/g, '')
      // Replace final letters with regular forms for relaxed matching
      .replace(/ך/g, 'כ')
      .replace(/ם/g, 'מ')
      .replace(/ן/g, 'נ')
      .replace(/ף/g, 'פ')
      .replace(/ץ/g, 'צ')
      // Remove special quotes and hyphens
      .replace(/["'״׳\-–_.,()/]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // Fetch store data
  async function loadData() {
    try {
      const response = await fetch('data/stores.json');
      if (!response.ok) throw new Error('Network response was not ok');
      storeData = await response.json();
    } catch (err) {
      console.warn('Failed to fetch data/stores.json directly, falling back:', err);
      // Fallback empty structure if fetch fails
      storeData = {
        metadata: {
          title: 'רשתות מכבדות בהצדעה',
          last_updated: new Date().toISOString(),
          available_cards: [],
          categories: []
        },
        stores: []
      };
    }

    allStores = storeData.stores || [];
    availableCards = storeData.metadata?.available_cards || [];

    // Set Total Count & Last Updated
    totalCountEl.textContent = allStores.length;
    if (storeData.metadata?.last_updated) {
      const d = new Date(storeData.metadata.last_updated);
      lastUpdatedDateEl.textContent = d.toLocaleDateString('he-IL', {
        year: 'numeric',
        month: 'numeric',
        day: 'numeric'
      });
    }

    populateCardsFilter();
    updateCategoryChips();
    applyViewMode(currentView);
    render();
  }

  // Populate Card Selector
  function populateCardsFilter() {
    cardFilterSelect.innerHTML = '<option value="all">כל הכרטיסים (הכל)</option>';
    availableCards.forEach(card => {
      const option = document.createElement('option');
      option.value = card.id || card.name;
      option.textContent = card.name + (card.discount_default ? ` (${card.discount_default})` : '');
      cardFilterSelect.appendChild(option);
    });
  }

  // Populate Categories
  function updateCategoryChips() {
    // Count stores per category considering card filter
    const catCounts = {};
    const relevantStores = currentCard === 'all' 
      ? allStores 
      : allStores.filter(s => s.cards?.some(c => (c.card_id === currentCard || c.card_name === currentCard)));

    relevantStores.forEach(s => {
      const cat = s.category || 'אחר';
      catCounts[cat] = (catCounts[cat] || 0) + 1;
    });

    const uniqueCategories = ['all', ...Object.keys(catCounts).sort()];

    categoryChipsContainer.innerHTML = '';
    uniqueCategories.forEach(cat => {
      const isAll = cat === 'all';
      const label = isAll ? 'הכל' : cat;
      const count = isAll ? relevantStores.length : (catCounts[cat] || 0);
      const isActive = currentCategory === cat;

      const btn = document.createElement('button');
      btn.className = `category-chip px-3.5 py-1.5 rounded-full font-medium transition text-xs flex items-center gap-1.5 whitespace-nowrap ${
        isActive 
          ? 'bg-blue-600 text-white shadow-xs' 
          : 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-600'
      }`;
      btn.dataset.category = cat;
      btn.innerHTML = `
        <span>${label}</span>
        <span class="category-count text-[10px] px-1.5 py-0.2 rounded-full ${
          isActive ? 'bg-blue-700 text-white' : 'bg-slate-200 dark:bg-slate-600 text-slate-600 dark:text-slate-300'
        }">${count}</span>
      `;
      btn.addEventListener('click', () => {
        currentCategory = cat;
        updateCategoryChips();
        render();
      });
      categoryChipsContainer.appendChild(btn);
    });
  }

  // Filter & Sort Logic
  function getFilteredStores() {
    const normalizedQuery = normalizeHebrew(searchQuery);

    let filtered = allStores.filter(store => {
      // 1. Card Filter
      if (currentCard !== 'all') {
        const hasCard = store.cards?.some(c => c.card_id === currentCard || c.card_name === currentCard);
        if (!hasCard) return false;
      }

      // 2. Category Filter
      if (currentCategory !== 'all') {
        if (store.category !== currentCategory) return false;
      }

      // 3. Search Query Filter
      if (normalizedQuery) {
        const storeNameNorm = normalizeHebrew(store.name);
        const catNorm = normalizeHebrew(store.category);
        const condNorm = normalizeHebrew(store.conditions);
        const cardsNorm = (store.cards || []).map(c => normalizeHebrew(c.card_name + ' ' + (c.notes || ''))).join(' ');

        const combinedText = `${storeNameNorm} ${catNorm} ${condNorm} ${cardsNorm}`;
        const queryTerms = normalizedQuery.split(' ').filter(Boolean);

        // Every term must appear in the combined text
        const matchesAllTerms = queryTerms.every(term => combinedText.includes(term));
        if (!matchesAllTerms) return false;
      }

      return true;
    });

    // Sorting
    filtered.sort((a, b) => {
      if (currentSort === 'discount-desc') {
        const discA = a.max_discount || 0;
        const discB = b.max_discount || 0;
        if (discB !== discA) return discB - discA;
        return a.name.localeCompare(b.name, 'he');
      } else if (currentSort === 'name-asc') {
        return a.name.localeCompare(b.name, 'he');
      } else if (currentSort === 'cards-desc') {
        const cardsA = a.cards?.length || 0;
        const cardsB = b.cards?.length || 0;
        if (cardsB !== cardsA) return cardsB - cardsA;
        return a.name.localeCompare(b.name, 'he');
      }
      return 0;
    });

    return filtered;
  }

  // Render Stores
  function render() {
    const stores = getFilteredStores();
    matchingCountEl.textContent = stores.length;

    // Update active filter badge
    const hasActiveFilters = currentCard !== 'all' || currentCategory !== 'all' || searchQuery.trim() !== '';
    if (hasActiveFilters) {
      activeFilterBadge.classList.remove('hidden');
      const activeParts = [];
      if (currentCard !== 'all') {
        const cardObj = availableCards.find(c => c.id === currentCard || c.name === currentCard);
        activeParts.push(cardObj ? cardObj.name : currentCard);
      }
      if (currentCategory !== 'all') activeParts.push(currentCategory);
      if (searchQuery.trim()) activeParts.push(`"${searchQuery.trim()}"`);
      activeFilterText.textContent = `מסונן לפי: ${activeParts.join(' • ')}`;
    } else {
      activeFilterBadge.classList.add('hidden');
    }

    if (stores.length === 0) {
      cardsView.classList.add('hidden');
      tableView.classList.add('hidden');
      noResultsEl.classList.remove('hidden');
    } else {
      noResultsEl.classList.add('hidden');
      if (currentView === 'grid') {
        cardsView.classList.remove('hidden');
        tableView.classList.add('hidden');
        renderCards(stores);
      } else {
        cardsView.classList.add('hidden');
        tableView.classList.remove('hidden');
        renderTable(stores);
      }
    }

    // Refresh Lucide Icons for newly injected elements
    if (window.lucide) {
      window.lucide.createIcons();
    }
  }

  // Render Grid Cards
  function renderCards(stores) {
    cardsView.innerHTML = '';

    stores.forEach(store => {
      const cardEl = document.createElement('div');
      cardEl.className = 'store-card bg-white dark:bg-slate-800 rounded-2xl p-5 border border-slate-200/80 dark:border-slate-700/80 shadow-xs flex flex-col justify-between hover:shadow-md transition-all duration-200';

      // Card Badges list
      const cardsHtml = (store.cards || []).map(c => `
        <div class="flex items-center justify-between text-xs py-1 px-2.5 rounded-lg bg-slate-50 dark:bg-slate-900/60 border border-slate-200/60 dark:border-slate-700/60">
          <span class="text-slate-600 dark:text-slate-300 font-medium truncate ml-2">${c.card_name}</span>
          <span class="font-bold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/70 px-1.5 py-0.5 rounded text-[11px]">${c.discount}</span>
        </div>
      `).join('');

      // Top bar with Logo, Category, Max discount badge
      cardEl.innerHTML = `
        <div class="space-y-3.5">
          <div class="flex items-start justify-between gap-3">
            <div class="w-12 h-12 rounded-xl bg-slate-100 dark:bg-slate-700 p-1.5 border border-slate-200 dark:border-slate-600 flex items-center justify-center flex-shrink-0">
              ${store.logo 
                ? `<img src="${store.logo}" alt="${store.name}" class="max-h-full max-w-full object-contain" onerror="this.parentElement.innerHTML='<i data-lucide=store class=\\'w-5 h-5 text-slate-400\\'></i>'; if(window.lucide) window.lucide.createIcons();" />` 
                : `<i data-lucide="store" class="w-5 h-5 text-slate-400"></i>`}
            </div>
            <div class="text-left">
              <span class="badge-discount-gold text-white font-extrabold text-xs px-2.5 py-1 rounded-lg inline-block">
                עד ${store.max_discount || 0}%
              </span>
            </div>
          </div>

          <div>
            <span class="text-[11px] font-medium text-blue-600 dark:text-blue-400 mb-0.5 block">${store.category || 'כללי'}</span>
            <h3 class="text-base font-bold text-slate-900 dark:text-white leading-snug">${store.name}</h3>
          </div>

          <div class="space-y-1.5 pt-1">
            <p class="text-[11px] text-slate-400 font-medium">כרטיסים משתתפים:</p>
            <div class="space-y-1.5">
              ${cardsHtml}
            </div>
          </div>

          ${store.conditions ? `
            <div class="pt-1">
              <p class="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 leading-relaxed" title="${store.conditions}">
                ${store.conditions}
              </p>
            </div>
          ` : ''}
        </div>

        <div class="pt-4 mt-3 border-t border-slate-100 dark:border-slate-700/60 flex items-center justify-between">
          <button class="details-btn text-xs font-semibold text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 flex items-center gap-1">
            <span>תנאים ופרטים</span>
            <i data-lucide="chevron-left" class="w-3.5 h-3.5"></i>
          </button>
          ${store.website ? `
            <a href="${store.website}" target="_blank" rel="noopener" class="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 flex items-center gap-1" title="לאתר הרשת">
              <i data-lucide="external-link" class="w-3.5 h-3.5"></i>
            </a>
          ` : ''}
        </div>
      `;

      cardEl.querySelector('.details-btn').addEventListener('click', () => openModal(store));
      cardsView.appendChild(cardEl);
    });
  }

  // Render Table Rows
  function renderTable(stores) {
    tableTbody.innerHTML = '';

    stores.forEach(store => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50/80 dark:hover:bg-slate-700/40 transition-colors';

      const cardsBadges = (store.cards || []).map(c => `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 mr-1 mb-1">
          <span>${c.card_name}:</span>
          <strong class="text-blue-600 dark:text-blue-400">${c.discount}</strong>
        </span>
      `).join('');

      tr.innerHTML = `
        <td class="py-3 px-4">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-lg bg-slate-100 dark:bg-slate-700 p-1 border border-slate-200 dark:border-slate-600 flex items-center justify-center flex-shrink-0">
              ${store.logo 
                ? `<img src="${store.logo}" alt="" class="max-h-full max-w-full object-contain" onerror="this.parentElement.innerHTML='<i data-lucide=store class=\\'w-4 h-4 text-slate-400\\'></i>'; if(window.lucide) window.lucide.createIcons();" />` 
                : `<i data-lucide="store" class="w-4 h-4 text-slate-400"></i>`}
            </div>
            <div>
              <span class="font-bold text-slate-900 dark:text-white block">${store.name}</span>
              ${store.website ? `<a href="${store.website}" target="_blank" class="text-[11px] text-blue-500 hover:underline">אתר רשת</a>` : ''}
            </div>
          </div>
        </td>
        <td class="py-3 px-4 text-slate-600 dark:text-slate-300">${store.category || 'כללי'}</td>
        <td class="py-3 px-4 text-center">
          <span class="font-extrabold text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/60 px-2 py-1 rounded-md text-xs border border-amber-200 dark:border-amber-800">
            עד ${store.max_discount || 0}%
          </span>
        </td>
        <td class="py-3 px-4">
          <div class="flex flex-wrap items-center">
            ${cardsBadges}
          </div>
        </td>
        <td class="py-3 px-4 text-center">
          <button class="table-details-btn p-1.5 rounded-lg text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition" title="צפה בפרטים">
            <i data-lucide="info" class="w-4 h-4"></i>
          </button>
        </td>
      `;

      tr.querySelector('.table-details-btn').addEventListener('click', () => openModal(store));
      tableTbody.appendChild(tr);
    });
  }

  // Open Details Modal
  function openModal(store) {
    modalTitle.textContent = store.name;
    modalCategory.textContent = store.category || 'כללי';

    if (store.logo) {
      modalLogo.src = store.logo;
      modalLogo.style.display = 'block';
    } else {
      modalLogo.style.display = 'none';
    }

    if (store.website) {
      modalWebsiteLink.href = store.website;
      modalWebsiteLink.classList.remove('hidden');
    } else {
      modalWebsiteLink.classList.add('hidden');
    }

    // Modal Cards list
    modalCardsList.innerHTML = '';
    (store.cards || []).forEach(c => {
      const cardRow = document.createElement('div');
      cardRow.className = 'p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200/70 dark:border-slate-700/60 space-y-1';
      cardRow.innerHTML = `
        <div class="flex items-center justify-between">
          <span class="font-semibold text-slate-800 dark:text-slate-100 text-sm">${c.card_name}</span>
          <span class="font-bold text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/60 px-2 py-0.5 rounded-md text-xs">${c.discount} הנחה</span>
        </div>
        ${c.notes ? `<p class="text-xs text-slate-500 dark:text-slate-400 leading-normal">${c.notes}</p>` : ''}
      `;
      modalCardsList.appendChild(cardRow);
    });

    // Conditions
    modalConditions.textContent = store.conditions || 'אין תנאים מיוחדים שצוינו עבור רשת זו.';

    storeModal.classList.remove('hidden');
    document.body.classList.add('overflow-hidden');
    if (window.lucide) window.lucide.createIcons();
  }

  // Close Modal
  function closeModal() {
    storeModal.classList.add('hidden');
    document.body.classList.remove('overflow-hidden');
  }

  // Apply View Mode
  function applyViewMode(mode) {
    currentView = mode;
    localStorage.setItem('behatsdaa_view', mode);

    if (mode === 'grid') {
      viewGridBtn.className = 'p-1.5 rounded-lg text-sm font-medium transition-all bg-white dark:bg-slate-700 shadow-xs text-blue-600 dark:text-blue-400';
      viewTableBtn.className = 'p-1.5 rounded-lg text-sm font-medium transition-all text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white';
    } else {
      viewTableBtn.className = 'p-1.5 rounded-lg text-sm font-medium transition-all bg-white dark:bg-slate-700 shadow-xs text-blue-600 dark:text-blue-400';
      viewGridBtn.className = 'p-1.5 rounded-lg text-sm font-medium transition-all text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white';
    }
  }

  // Event Listeners
  function setupEventListeners() {
    // Search input
    searchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value;
      if (searchQuery) {
        clearSearchBtn.classList.remove('hidden');
      } else {
        clearSearchBtn.classList.add('hidden');
      }
      render();
    });

    clearSearchBtn.addEventListener('click', () => {
      searchInput.value = '';
      searchQuery = '';
      clearSearchBtn.classList.add('hidden');
      searchInput.focus();
      render();
    });

    // Card select
    cardFilterSelect.addEventListener('change', (e) => {
      currentCard = e.target.value;
      updateCategoryChips();
      render();
    });

    // Sort select
    sortSelect.addEventListener('change', (e) => {
      currentSort = e.target.value;
      render();
    });

    // Reset filters
    const resetAll = () => {
      currentCard = 'all';
      currentCategory = 'all';
      searchQuery = '';
      searchInput.value = '';
      clearSearchBtn.classList.add('hidden');
      cardFilterSelect.value = 'all';
      updateCategoryChips();
      render();
    };

    resetFiltersBtn.addEventListener('click', resetAll);
    clearFiltersBtn.addEventListener('click', resetAll);

    // View toggle buttons
    viewGridBtn.addEventListener('click', () => {
      applyViewMode('grid');
      render();
    });
    viewTableBtn.addEventListener('click', () => {
      applyViewMode('table');
      render();
    });

    // Theme toggle
    themeToggleBtn.addEventListener('click', toggleTheme);

    // Modal close listeners
    modalCloseBtn.addEventListener('click', closeModal);
    modalDismissBtn.addEventListener('click', closeModal);
    storeModal.addEventListener('click', (e) => {
      if (e.target === storeModal) closeModal();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !storeModal.classList.contains('hidden')) {
        closeModal();
      }
    });
  }

  // Startup
  initTheme();
  setupEventListeners();
  loadData();

})();

