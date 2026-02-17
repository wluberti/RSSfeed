/**
 * FeedFlow — RSS Feed Reader Application
 *
 * Client-side logic for managing feeds, articles, search, and theming.
 */

(function () {
    "use strict";

    // --- State ---
    let feeds = [];
    let currentFeedId = null; // null = "All Articles"
    let currentSort = "date";
    let currentOrder = "desc";
    let currentLayout = "tile"; // 'tile' or 'list'
    let searchDebounce = null;

    // --- DOM References ---
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const searchInput = $("#searchInput");
    const searchClear = $("#searchClear");
    const feedList = $("#feedList");
    const feedListEmpty = $("#feedListEmpty");
    const articlesContainer = $("#articlesContainer");
    const articlesEmpty = $("#articlesEmpty");
    const themeToggle = $("#themeToggle");
    const refreshAllBtn = $("#refreshAllBtn");
    const addFeedBtn = $("#addFeedBtn");
    const addFeedModal = $("#addFeedModal");
    const addFeedModalClose = $("#addFeedModalClose");
    const feedUrlInput = $("#feedUrlInput");
    const addFeedError = $("#addFeedError");
    const addFeedCancelBtn = $("#addFeedCancelBtn");
    const addFeedSubmitBtn = $("#addFeedSubmitBtn");
    const webSearchInput = $("#webSearchInput");
    const webSearchBtn = $("#webSearchBtn");
    const webSearchModal = $("#webSearchModal");
    const webSearchModalClose = $("#webSearchModalClose");
    const webSearchResults = $("#webSearchResults");
    const webSearchLoading = $("#webSearchLoading");
    const webSearchEmpty = $("#webSearchEmpty");
    const sortSelect = $("#sortSelect");
    const sortOrderBtn = $("#sortOrderBtn");
    const filterAll = $("#filterAll");
    const viewTileBtn = $("#viewTileBtn");
    const viewListBtn = $("#viewListBtn");
    const toastContainer = $("#toastContainer");
    const confirmModal = $("#confirmModal");
    const confirmModalTitle = $("#confirmModalTitle");
    const confirmModalMessage = $("#confirmModalMessage");
    const confirmOkBtn = $("#confirmOkBtn");
    const confirmCancelBtn = $("#confirmCancelBtn");

    // --- API Helpers ---

    /**
     * Make an API request.
     * @param {string} endpoint - API path.
     * @param {object} options - Fetch options.
     * @returns {Promise<object>} Parsed JSON response.
     */
    async function api(endpoint, options = {}) {
        const defaults = {
            headers: { "Content-Type": "application/json" },
        };
        const res = await fetch(endpoint, { ...defaults, ...options });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || `Request failed (${res.status})`);
        }
        return data;
    }

    // --- Theme ---

    /**
     * Initialize theme from localStorage or default to light.
     */
    function initTheme() {
        const saved = localStorage.getItem("feedflow-theme") || "light";
        document.documentElement.setAttribute("data-theme", saved);
    }

    /**
     * Toggle between light and dark themes.
     */
    function toggleTheme() {
        const current = document.documentElement.getAttribute("data-theme");
        const next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("feedflow-theme", next);
    }

    // --- Toasts ---

    /**
     * Show a toast notification.
     * @param {string} message - Toast message.
     * @param {string} type - Toast type: 'success', 'error', 'info'.
     */
    function showToast(message, type = "info") {
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <span>${escapeHtml(message)}</span>
            <button class="toast-close">&times;</button>
        `;
        toastContainer.appendChild(toast);

        toast.querySelector(".toast-close").addEventListener("click", () => {
            toast.remove();
        });

        setTimeout(() => {
            if (toast.parentNode) toast.remove();
        }, 4000);
    }

    // --- Confirm Modal ---

    /**
     * Show a custom confirmation modal.
     * @param {string} title - Modal title.
     * @param {string} message - Confirmation message.
     * @returns {Promise<boolean>} Resolves true if confirmed, false if cancelled.
     */
    function showConfirm(title, message) {
        return new Promise((resolve) => {
            confirmModalTitle.textContent = title;
            confirmModalMessage.textContent = message;
            confirmModal.classList.add("active");
            confirmOkBtn.focus();

            function cleanup(result) {
                confirmModal.classList.remove("active");
                confirmOkBtn.removeEventListener("click", onOk);
                confirmCancelBtn.removeEventListener("click", onCancel);
                confirmModal.removeEventListener("click", onOverlay);
                resolve(result);
            }

            function onOk() { cleanup(true); }
            function onCancel() { cleanup(false); }
            function onOverlay(e) {
                if (e.target === confirmModal) cleanup(false);
            }

            confirmOkBtn.addEventListener("click", onOk);
            confirmCancelBtn.addEventListener("click", onCancel);
            confirmModal.addEventListener("click", onOverlay);
        });
    }

    // --- Feed List ---

    let isYoutubeCollapsed = true;
    let isYoutubeListExpanded = false;
    const YOUTUBE_LIMIT = 15;

    /**
     * Load and render all feeds from the API.
     */
    async function loadFeeds() {
        try {
            feeds = await api("/api/feeds");
            renderFeedList();
        } catch (err) {
            showToast("Failed to load feeds: " + err.message, "error");
        }
    }

    /**
     * Helper to create a feed item DOM element
     */
    function createFeedItem(feed) {
        const item = document.createElement("div");
        item.className = `feed-item${currentFeedId === feed.id ? " active" : ""}`;
        item.dataset.feedId = feed.id;

        const iconHtml = feed.image_url
            ? `<img class="feed-item-icon" src="${escapeHtml(feed.image_url)}" alt="" onerror="this.outerHTML='<div class=\\'feed-item-icon-placeholder\\'>${escapeHtml(feed.title.charAt(0).toUpperCase())}</div>'">`
            : `<div class="feed-item-icon-placeholder">${escapeHtml(feed.title.charAt(0).toUpperCase())}</div>`;

        item.innerHTML = `
            ${iconHtml}
            <div class="feed-item-info">
                <div class="feed-item-title" title="${escapeHtml(feed.title)}">${escapeHtml(feed.title)}</div>
                <div class="feed-item-count">${feed.article_count || 0} articles</div>
            </div>
            <div class="feed-item-actions">
                <button class="btn btn-icon refresh-feed-btn" title="Refresh">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"></polyline>
                        <polyline points="1 20 1 14 7 14"></polyline>
                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                    </svg>
                </button>
                <button class="btn btn-icon remove-feed-btn" title="Remove feed" style="color: var(--color-danger);">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                </button>
            </div>
        `;

        // Click to filter by this feed
        item.addEventListener("click", (e) => {
            if (e.target.closest(".feed-item-actions")) return;
            currentFeedId = feed.id;
            // Re-render to update active state, but keep collapse state
            renderFeedList();
            loadArticles();
            updateFilterButtons();
        });

        // Refresh single feed
        item.querySelector(".refresh-feed-btn").addEventListener("click", async (e) => {
            e.stopPropagation(); // Prevent item click
            const btn = e.target.closest(".refresh-feed-btn");
            btn.innerHTML = '<div class="spinner" style="width:12px;height:12px;border-width:2px"></div>';
            try {
                await api(`/api/feeds/${feed.id}/refresh`, { method: "POST" });
                showToast(`Refreshed "${feed.title}"`, "success");
                await loadFeeds();
                await loadArticles();
            } catch (err) {
                showToast("Refresh failed: " + err.message, "error");
                btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>';
            }
        });

        // Remove feed
        item.querySelector(".remove-feed-btn").addEventListener("click", async (e) => {
            e.stopPropagation(); // Prevent item click
            const confirmed = await showConfirm(
                "Remove Feed",
                `Remove "${feed.title}" and all its articles?`
            );
            if (!confirmed) return;
            try {
                await api(`/api/feeds/${feed.id}`, { method: "DELETE" });
                showToast(`Removed "${feed.title}"`, "success");
                if (currentFeedId === feed.id) {
                    currentFeedId = null;
                    updateFilterButtons();
                }
                await loadFeeds();
                await loadArticles();
            } catch (err) {
                showToast("Remove failed: " + err.message, "error");
            }
        });

        return item;
    }

    /**
     * Render the feed list in the sidebar.
     */
    function renderFeedList() {
        // Keep empty state visibility in sync
        if (feeds.length === 0) {
            feedListEmpty.style.display = "flex";
            feedList.innerHTML = "";
            feedList.appendChild(feedListEmpty);
            return;
        }
        feedListEmpty.style.display = "none";

        // Separate YouTube feeds
        const youtubeFeeds = feeds.filter(f =>
            (f.url && f.url.includes("youtube.com")) ||
            (f.site_url && f.site_url.includes("youtube.com"))
        );
        const otherFeeds = feeds.filter(f => !youtubeFeeds.includes(f));

        const fragment = document.createDocumentFragment();

        // 1. Render standard feeds
        otherFeeds.forEach((feed) => {
            fragment.appendChild(createFeedItem(feed));
        });

        // 2. Render grouped YouTube feeds if any
        if (youtubeFeeds.length > 0) {
            const groupHeader = document.createElement("div");
            groupHeader.className = `feed-group-header${currentFeedId === 'youtube-all' ? ' active' : ''}`;
            groupHeader.style.cssText = "display:flex;align-items:center;padding:8px 12px;cursor:pointer;font-weight:600;font-size:0.9rem;color:var(--text-secondary);user-select:none;margin-top:8px;";
            // Highlight if active
            if (currentFeedId === 'youtube-all') {
                groupHeader.style.backgroundColor = "var(--bg-hover)";
                groupHeader.style.color = "var(--color-primary)";
            }

            const arrowTransform = isYoutubeCollapsed ? "0deg" : "90deg";

            groupHeader.innerHTML = `
                <svg class="group-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16" style="margin-right:8px;transition:transform 0.2s;transform:rotate(${arrowTransform})">
                    <polyline points="9 18 15 12 9 6"></polyline>
                </svg>
                <span class="group-title-text" title="Show all YouTube subscriptions">YouTube Subscriptions</span>
                <span style="margin-left:auto;font-size:0.8rem;opacity:0.7;margin-right:8px;">${youtubeFeeds.length}</span>
                <div class="feed-item-actions" style="display:flex;gap:2px;">
                    <button class="btn btn-icon yt-refresh-all-btn" title="Refresh all subscriptions" style="width:28px;height:28px;">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                            <polyline points="23 4 23 10 17 10"></polyline>
                            <polyline points="1 20 1 14 7 14"></polyline>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                        </svg>
                    </button>
                    <button class="btn btn-icon yt-remove-all-btn" title="Remove all subscriptions" style="color:var(--color-danger);width:28px;height:28px;">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>
                </div>
            `;

            const groupContainer = document.createElement("div");
            groupContainer.className = "feed-group-container";
            groupContainer.style.display = isYoutubeCollapsed ? "none" : "block";
            groupContainer.style.paddingLeft = "0";

            // List Truncation Logic
            const visibleFeeds = isYoutubeListExpanded ? youtubeFeeds : youtubeFeeds.slice(0, YOUTUBE_LIMIT);

            visibleFeeds.forEach((feed) => {
                const item = createFeedItem(feed);
                groupContainer.appendChild(item);
            });

            // Header Click -> Toggle Collapse (Arrow) / Filter All (Text)
            const arrowBtn = groupHeader.querySelector(".group-arrow");
            const titleText = groupHeader.querySelector(".group-title-text");

            // Toggle collapse
            const toggleCollapse = (e) => {
                e.stopPropagation();
                isYoutubeCollapsed = !isYoutubeCollapsed;
                renderFeedList(); // Re-render to update UI
            };
            arrowBtn.addEventListener("click", toggleCollapse);

            // Filter all YouTube feeds
            titleText.addEventListener("click", (e) => {
                e.stopPropagation();
                currentFeedId = 'youtube-all';
                renderFeedList();
                loadArticles();
                updateFilterButtons();
            });

            groupHeader.addEventListener("click", (e) => {
                // If clicked arrow, title, or action buttons, handled separately.
                if (e.target.closest(".group-arrow") || e.target.closest(".group-title-text") || e.target.closest(".feed-item-actions")) return;

                currentFeedId = 'youtube-all';
                if (isYoutubeCollapsed) isYoutubeCollapsed = false; // Auto-expand
                renderFeedList();
                loadArticles();
                updateFilterButtons();
            });

            // Refresh All YouTube Subscriptions
            groupHeader.querySelector(".yt-refresh-all-btn").addEventListener("click", async (e) => {
                e.stopPropagation();
                const btn = e.target.closest(".yt-refresh-all-btn");
                btn.innerHTML = '<div class="spinner" style="width:12px;height:12px;border-width:2px"></div>';
                showToast(`Refreshing ${youtubeFeeds.length} subscriptions...`, "info");
                let successCount = 0;
                let failCount = 0;
                for (const feed of youtubeFeeds) {
                    try {
                        await api(`/api/feeds/${feed.id}/refresh`, { method: "POST" });
                        successCount++;
                    } catch {
                        failCount++;
                    }
                }
                showToast(`Refreshed ${successCount}/${youtubeFeeds.length} subscriptions${failCount ? ` (${failCount} failed)` : ''}`, successCount > 0 ? "success" : "error");
                await loadFeeds();
                await loadArticles();
            });

            // Remove All YouTube Subscriptions
            groupHeader.querySelector(".yt-remove-all-btn").addEventListener("click", async (e) => {
                e.stopPropagation();
                const confirmed = await showConfirm(
                    "Remove All Subscriptions",
                    `Remove all ${youtubeFeeds.length} YouTube subscriptions and their articles?`
                );
                if (!confirmed) return;
                showToast(`Removing ${youtubeFeeds.length} subscriptions...`, "info");
                let successCount = 0;
                for (const feed of youtubeFeeds) {
                    try {
                        await api(`/api/feeds/${feed.id}`, { method: "DELETE" });
                        successCount++;
                    } catch { /* skip */ }
                }
                if (currentFeedId === 'youtube-all') {
                    currentFeedId = null;
                    updateFilterButtons();
                }
                showToast(`Removed ${successCount} subscriptions`, "success");
                await loadFeeds();
                await loadArticles();
            });

            // "Show more..." / "Show less" toggle
            if (youtubeFeeds.length > YOUTUBE_LIMIT) {
                const toggleItem = document.createElement("div");
                toggleItem.style.padding = "8px 12px";
                toggleItem.style.fontSize = "0.8rem";
                toggleItem.style.color = "var(--text-tertiary)";
                toggleItem.style.fontStyle = "italic";
                toggleItem.style.cursor = "pointer";
                toggleItem.className = "youtube-toggle-more"; // For potential styling

                if (!isYoutubeListExpanded) {
                    toggleItem.textContent = `...show ${youtubeFeeds.length - YOUTUBE_LIMIT} more`;
                    toggleItem.addEventListener("click", (e) => {
                        e.stopPropagation();
                        isYoutubeListExpanded = true;
                        renderFeedList();
                    });
                     groupContainer.appendChild(toggleItem);
                } else {
                    // Start of list is already rendered above
                    // Make "Show less" appear at the END of the list
                    toggleItem.textContent = "Show less";
                    toggleItem.style.textAlign = "center";
                    toggleItem.addEventListener("click", (e) => {
                         e.stopPropagation();
                         isYoutubeListExpanded = false;
                         renderFeedList();
                         // Scroll back to top of group? Optional.
                    });
                    groupContainer.appendChild(toggleItem);
                }
            }

            fragment.appendChild(groupHeader);
            fragment.appendChild(groupContainer);
        }

        // Replace existing feed items (keep empty placeholder ref)
        feedList.innerHTML = "";
        feedList.appendChild(feedListEmpty);
        feedList.appendChild(fragment);
    }

    /**
     * Update the active state of filter buttons.
     */
    function updateFilterButtons() {
        filterAll.classList.toggle("active", currentFeedId === null);
        feedList.querySelectorAll(".feed-item").forEach((el) => {
            el.classList.toggle("active", parseInt(el.dataset.feedId) === currentFeedId);
        });
        // Handle YouTube group header active state
        const groupHeader = feedList.querySelector(".feed-group-header");
        if (groupHeader) {
            if (currentFeedId === 'youtube-all') {
                groupHeader.classList.add("active");
                groupHeader.style.backgroundColor = "var(--bg-hover)";
                groupHeader.style.color = "var(--color-primary)";
            } else {
                groupHeader.classList.remove("active");
                groupHeader.style.backgroundColor = ""; // Reset
                groupHeader.style.color = "var(--text-secondary)";
            }
        }
    }

    // --- Articles ---

    /**
     * Load and render articles from the API.
     */
    async function loadArticles() {
        try {
            const params = new URLSearchParams({
                sort: currentSort,
                order: currentOrder,
            });

            const query = searchInput.value.trim();
            if (query) {
                // Search always across all feeds
                params.set("q", query);
            } else if (currentFeedId === 'youtube-all') {
                 // Filter by YouTube group
                 params.set("group", "youtube");
            } else if (currentFeedId !== null) {
                // Only filter by feed when not searching
                params.set("feed_id", currentFeedId);
            }

            const articles = await api(`/api/articles?${params}`);
            renderArticles(articles);
        } catch (err) {
            showToast("Failed to load articles: " + err.message, "error");
        }
    }

    /**
     * Toggle a card between short and full description (tile view only).
     * @param {HTMLElement} card - The article card element.
     */
    function toggleViewMode(card) {
        const isShort = card.classList.contains("view-short");
        card.classList.remove("view-short", "view-full");
        card.classList.add(isShort ? "view-full" : "view-short");
    }

    /**
     * Render article cards in the main content area.
     * @param {Array} articles - Array of article objects.
     */
    function renderArticles(articles) {
        // Clear
        articlesContainer.innerHTML = "";

        if (articles.length === 0) {
            articlesContainer.innerHTML = `
                <div class="articles-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="64" height="64">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                        <line x1="16" y1="13" x2="8" y2="13"></line>
                        <line x1="16" y1="17" x2="8" y2="17"></line>
                    </svg>
                    <h3>No articles found</h3>
                    <p>${searchInput.value.trim() ? "Try a different search term" : "Add a feed to start reading"}</p>
                </div>
            `;
            return;
        }

        const fragment = document.createDocumentFragment();
        articles.forEach((article) => {
            const card = document.createElement("article");
            card.className = "article-card view-short";

            const dateStr = formatDate(article.pub_date);
            const fullDescription = stripHtml(article.description);

            card.innerHTML = `
                <div class="article-card-header">
                    <div class="article-card-feed">
                        ${article.feed_image ? `<img src="${escapeHtml(article.feed_image)}" class="article-feed-icon" alt="" onerror="this.style.display='none'">` : ""}
                        <span class="article-card-feed-dot" ${article.feed_image ? 'style="display:none"' : ""}></span>
                        <span>${escapeHtml(article.feed_title || "")}</span>
                    </div>
                    <time class="article-card-date" datetime="${escapeHtml(article.pub_date)}">${dateStr}</time>
                    ${article.link ? `<a class="article-card-link header-link" href="${escapeHtml(article.link)}" target="_blank" rel="noopener noreferrer">
                        Read article
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                            <polyline points="15 3 21 3 21 9"></polyline>
                            <line x1="10" y1="14" x2="21" y2="3"></line>
                        </svg>
                    </a>` : ""}
                </div>
                ${article.thumbnail ? `<img src="${escapeHtml(article.thumbnail)}" class="article-card-thumbnail" alt="" onerror="this.style.display='none'" loading="lazy">` : ""}
                <div class="article-content-wrapper">
                    <div class="article-card-title-row">
                        <h3 class="article-card-title">
                            ${article.feed_image ? `<img src="${escapeHtml(article.feed_image)}" class="article-title-icon" alt="" onerror="this.style.display='none'">` : ""}
                            <span>${escapeHtml(article.title)}</span>
                        </h3>
                        <time class="article-card-date-inline" datetime="${escapeHtml(article.pub_date)}">${dateStr}</time>
                    </div>
                    ${fullDescription ? `<p class="article-card-description">${escapeHtml(fullDescription)}</p>` : ""}
                </div>
                <div class="article-card-footer">
                    <div class="article-card-meta">
                        ${article.category ? `<span class="article-tag">${escapeHtml(article.category)}</span>` : ""}
                        ${article.author ? `<span class="article-author">by ${escapeHtml(article.author)}</span>` : ""}
                    </div>
                    ${article.link ? `<a class="article-card-link footer-link" href="${escapeHtml(article.link)}" target="_blank" rel="noopener noreferrer">
                        Read article
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                            <polyline points="15 3 21 3 21 9"></polyline>
                            <line x1="10" y1="14" x2="21" y2="3"></line>
                        </svg>
                    </a>` : ""}
                </div>
                <div class="article-card-view-hint">Click to expand</div>
            `;

            // Click card to toggle view in both layouts
            card.addEventListener("click", (e) => {
                if (e.target.closest(".article-card-link")) return;
                if (currentLayout === "list") {
                    card.classList.toggle("list-expanded");
                } else {
                    toggleViewMode(card);
                }
            });

            fragment.appendChild(card);
        });

        articlesContainer.appendChild(fragment);
    }

    // --- Add Feed ---

    /**
     * Open the Add Feed modal.
     */
    function openAddFeedModal() {
        feedUrlInput.value = "";
        addFeedError.textContent = "";
        addFeedModal.classList.add("active");
        feedUrlInput.focus();
    }

    /**
     * Close the Add Feed modal.
     */
    function closeAddFeedModal() {
        addFeedModal.classList.remove("active");
    }

    /**
     * Submit a new feed URL.
     */
    async function submitAddFeed() {
        const url = feedUrlInput.value.trim();
        if (!url) {
            addFeedError.textContent = "Please enter a feed URL";
            return;
        }

        addFeedError.textContent = "";
        addFeedSubmitBtn.disabled = true;
        addFeedSubmitBtn.querySelector(".btn-text").textContent = "Adding...";
        addFeedSubmitBtn.querySelector(".btn-spinner").style.display = "inline-block";

        try {
            const result = await api("/api/feeds", {
                method: "POST",
                body: JSON.stringify({ url }),
            });
            showToast(`Added "${result.feed.title}" (${result.articles_added} articles)`, "success");
            closeAddFeedModal();
            await loadFeeds();
            // Auto-select the newly added feed
            currentFeedId = result.feed.id;
            renderFeedList();
            updateFilterButtons();
            await loadArticles();
        } catch (err) {
            addFeedError.textContent = err.message;
        } finally {
            addFeedSubmitBtn.disabled = false;
            addFeedSubmitBtn.querySelector(".btn-text").textContent = "Add Feed";
            addFeedSubmitBtn.querySelector(".btn-spinner").style.display = "none";
        }
    }

    // --- Web Search ---

    // Additional DOM references for search filters
    const webSearchSiteFilter = $("#webSearchSiteFilter");
    const webSearchFeedFilter = $("#webSearchFeedFilter");



    /**
     * Perform a web search for RSS feeds.
     */
    async function performWebSearch() {
        const query = webSearchInput.value.trim();
        const siteFilter = webSearchSiteFilter.value.trim();
        const feedFilter = webSearchFeedFilter.value.trim();

        if (!query) {
            showToast("Please enter a search query", "info");
            return;
        }

        webSearchModal.classList.add("active");
        webSearchLoading.style.display = "flex";
        webSearchEmpty.style.display = "none";
        // Remove any previous results
        webSearchResults.querySelectorAll(".search-result-item").forEach((el) => el.remove());

        try {
            const params = new URLSearchParams({ q: query });
            if (siteFilter) params.append("site", siteFilter);
            if (feedFilter) params.append("feed", feedFilter);

            const results = await api(`/api/search/web?${params.toString()}`);
            webSearchLoading.style.display = "none";

            if (results.length === 0) {
                webSearchEmpty.style.display = "block";
                webSearchEmpty.innerHTML = "<p>No feeds found. Try a different search term.</p>";
                return;
            }

            const fragment = document.createDocumentFragment();
            results.forEach((result) => {
                const item = document.createElement("div");
                item.className = "search-result-item";

                const siteUrl = escapeHtml(result.site_url || "");
                const description = escapeHtml(result.description || "");
                const hasFeed = !!result.feed_url;

                item.innerHTML = `
                    <div class="search-result-info">
                        <div class="search-result-title">${escapeHtml(result.title)}</div>
                        <a class="search-result-url" href="${siteUrl}" target="_blank" rel="noopener">${siteUrl} ↗</a>
                        ${description ? `<div class="search-result-description">${description}</div>` : ""}
                    </div>
                    <button class="btn btn-sm ${hasFeed ? "btn-primary" : "btn-secondary"} add-search-result-btn"
                            ${hasFeed ? "" : "disabled"}>${hasFeed ? "Add" : "No feed"}</button>
                `;

                if (hasFeed) {
                    item.querySelector(".add-search-result-btn").addEventListener("click", async (e) => {
                        const btn = e.target;
                        btn.disabled = true;
                        btn.textContent = "Adding...";
                        try {
                            const addResult = await api("/api/feeds", {
                                method: "POST",
                                body: JSON.stringify({ url: result.feed_url }),
                            });
                            btn.textContent = "Added ✓";
                            btn.classList.remove("btn-primary");
                            btn.classList.add("btn-secondary");
                            showToast(`Added "${addResult.feed.title}"`, "success");
                            await loadFeeds();
                            await loadArticles();
                        } catch (err) {
                            btn.disabled = false;
                            btn.textContent = "Add";
                            showToast(err.message, "error");
                        }
                    });
                }

                fragment.appendChild(item);
            });

            webSearchResults.appendChild(fragment);
        } catch (err) {
            webSearchLoading.style.display = "none";
            webSearchEmpty.style.display = "block";
            webSearchEmpty.innerHTML = `<p>Search failed: ${escapeHtml(err.message)}</p>`;
        }
    }

    // --- Refresh All ---

    /**
     * Refresh all stored feeds.
     */
    async function refreshAllFeeds() {
        document.body.classList.add("refreshing");
        refreshAllBtn.disabled = true;

        try {
            await api("/api/feeds/refresh", { method: "POST" });
            showToast("All feeds refreshed", "success");
            await loadFeeds();
            await loadArticles();
        } catch (err) {
            showToast("Refresh failed: " + err.message, "error");
        } finally {
            document.body.classList.remove("refreshing");
            refreshAllBtn.disabled = false;
        }
    }

    // --- Utilities ---

    /**
     * Escape HTML special characters.
     * @param {string} str - Input string.
     * @returns {string} Escaped string.
     */
    function escapeHtml(str) {
        if (!str) return "";
        const div = document.createElement("div");
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    /**
     * Strip HTML tags from a string.
     * @param {string} html - HTML string.
     * @returns {string} Plain text.
     */
    function stripHtml(html) {
        if (!html) return "";
        const div = document.createElement("div");
        div.innerHTML = html;
        return div.textContent || div.innerText || "";
    }

    /**
     * Format an ISO date string for display.
     * @param {string} dateStr - ISO 8601 date string.
     * @returns {string} Formatted date string.
     */
    function formatDate(dateStr) {
        if (!dateStr) return "";
        try {
            const date = new Date(dateStr);
            const now = new Date();
            const diff = now - date;
            const mins = Math.floor(diff / 60000);
            const hours = Math.floor(diff / 3600000);
            const days = Math.floor(diff / 86400000);

            if (mins < 1) return "just now";
            if (mins < 60) return `${mins}m ago`;
            if (hours < 24) return `${hours}h ago`;
            if (days < 7) return `${days}d ago`;

            return date.toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
                year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
            });
        } catch {
            return dateStr;
        }
    }

    // --- Event Bindings ---

    function bindEvents() {
        // Theme toggle
        themeToggle.addEventListener("click", toggleTheme);

        // Search
        searchInput.addEventListener("input", () => {
            searchClear.classList.toggle("visible", searchInput.value.length > 0);
            clearTimeout(searchDebounce);
            searchDebounce = setTimeout(loadArticles, 300);
        });
        searchClear.addEventListener("click", () => {
            searchInput.value = "";
            searchClear.classList.remove("visible");
            loadArticles();
        });

        // Filter all
        filterAll.addEventListener("click", () => {
            currentFeedId = null;
            updateFilterButtons();
            loadArticles();
        });

        // Sorting
        sortSelect.addEventListener("change", () => {
            currentSort = sortSelect.value;
            loadArticles();
        });

        sortOrderBtn.addEventListener("click", () => {
            currentOrder = currentOrder === "desc" ? "asc" : "desc";
            sortOrderBtn.dataset.order = currentOrder;
            loadArticles();
        });

        // Layout toggle
        viewTileBtn.addEventListener("click", () => {
            currentLayout = "tile";
            articlesContainer.classList.remove("layout-list");
            viewTileBtn.dataset.active = "true";
            viewListBtn.dataset.active = "false";
        });

        viewListBtn.addEventListener("click", () => {
            currentLayout = "list";
            articlesContainer.classList.add("layout-list");
            viewListBtn.dataset.active = "true";
            viewTileBtn.dataset.active = "false";
        });

        // Refresh all
        refreshAllBtn.addEventListener("click", refreshAllFeeds);

        // Add feed modal
        addFeedBtn.addEventListener("click", openAddFeedModal);
        addFeedModalClose.addEventListener("click", closeAddFeedModal);
        addFeedCancelBtn.addEventListener("click", closeAddFeedModal);
        addFeedSubmitBtn.addEventListener("click", submitAddFeed);
        feedUrlInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") submitAddFeed();
        });
        addFeedModal.addEventListener("click", (e) => {
            if (e.target === addFeedModal) closeAddFeedModal();
        });

        // Web search
        webSearchBtn.addEventListener("click", performWebSearch);
        webSearchInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") performWebSearch();
        });
        webSearchModalClose.addEventListener("click", () => {
            webSearchModal.classList.remove("active");
        });
        webSearchModal.addEventListener("click", (e) => {
            if (e.target === webSearchModal) webSearchModal.classList.remove("active");
        });

        // Keyboard shortcuts
        document.addEventListener("keydown", (e) => {
            // Escape to close modals
            if (e.key === "Escape") {
                if (addFeedModal.classList.contains("active")) closeAddFeedModal();
                if (webSearchModal.classList.contains("active"))
                    webSearchModal.classList.remove("active");
            }
            // Ctrl/Cmd + K to focus search
            if ((e.ctrlKey || e.metaKey) && e.key === "k") {
                e.preventDefault();
                searchInput.focus();
            }
        });
    }

    // --- Import Feeds ---

    const importFeedBtn = $("#importFeedBtn");
    const importFileInput = $("#importFileInput");

    // Modal elements
    const importHelpModal = $("#importHelpModal");
    const importHelpModalClose = $("#importHelpModalClose");
    const importHelpCancelBtn = $("#importHelpCancelBtn");
    const importHelpUploadBtn = $("#importHelpUploadBtn");

    function bindImportEvents() {
        if (!importFeedBtn || !importFileInput) return;

        // Open Modal
        importFeedBtn.addEventListener("click", () => {
            importHelpModal.classList.add("active");
        });

        // Close Modal
        const closeModal = () => importHelpModal.classList.remove("active");
        if (importHelpModalClose) importHelpModalClose.addEventListener("click", closeModal);
        if (importHelpCancelBtn) importHelpCancelBtn.addEventListener("click", closeModal);

        // Upload Action
        if (importHelpUploadBtn) {
            importHelpUploadBtn.addEventListener("click", () => {
                closeModal();
                importFileInput.click();
            });
        }

        // Close on background click
        importHelpModal.addEventListener("click", (e) => {
            if (e.target === importHelpModal) closeModal();
        });

        importFileInput.addEventListener("change", async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            // Simple validation
            if (!file.name.endsWith(".csv")) {
                showToast("Please select a .csv file", "error");
                importFileInput.value = ""; // Reset
                return;
            }

            const formData = new FormData();
            formData.append("file", file);

            // Show loading toast
            showToast("Importing feeds...", "info");

            try {
                const res = await fetch("/api/feeds/import", {
                    method: "POST",
                    body: formData,
                });
                const data = await res.json();

                if (!res.ok) {
                    throw new Error(data.error || "Import failed");
                }

                showToast(`Imported ${data.imported_count} feeds. Errors: ${data.error_count}`, "success");

                // Refresh feeds
                await loadFeeds();
                await loadArticles();

            } catch (err) {
                showToast("Import error: " + err.message, "error");
            } finally {
                // Reset input
                importFileInput.value = "";
            }
        });
    }

    // --- Init ---

    function init() {
        initTheme();
        bindEvents();
        bindImportEvents();
        loadFeeds();
        loadArticles();
    }

    // Run when DOM is ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

})();
