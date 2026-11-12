/**
 * PayShield AI — Product Search
 * Clean product search with real results from the backend assistant service.
 * No mock data: all offers come from /assistant/recommendations.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PageId } from '../../types';
import {
  getAssistantRecommendations,
  mapChannel3Result,
  ProductOffer,
  ShoppingQueryRequest,
} from '../../services/api';
import { EmptyState } from '../common/EmptyState';
import { formatAmount } from '../../utils/dateHelpers';

const CATEGORIES = ['all', 'electronics', 'software', 'services', 'other'];
const SORTS = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'price-asc', label: 'Price: low to high' },
  { value: 'price-desc', label: 'Price: high to low' },
];

export const ProductSearchPage: React.FC<{
  currentCluster: string;
  onNavigate: (page: PageId, pendingIntent?: any) => void;
}> = ({ onNavigate }) => {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [sort, setSort] = useState('relevance');
  const [pageSize, setPageSize] = useState(12);

  const [offers, setOffers] = useState<ProductOffer[]>([]);
  const [nextPageToken, setNextPageToken] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const compareRef = useRef<Set<string>>(new Set());
  const compare = useMemo(() => {
    const ids = Array.from(compareRef.current);
    return offers.filter((o) => ids.includes(o.id));
  }, [offers, compareRef]);

  const filtered = useMemo(() => {
    let list = offers;
    if (category !== 'all') list = list.filter((o) => o.category === category);
    if (verifiedOnly) list = list.filter((o) => o.verification === 'VERIFIED_MERCHANT');
    if (sort === 'price-asc') list = [...list].sort((a, b) => a.price - b.price);
    if (sort === 'price-desc') list = [...list].sort((a, b) => b.price - a.price);
    return list;
  }, [offers, category, verifiedOnly, sort]);

  const handleSearch = useCallback(
    async (q: string, token?: string, append = false) => {
      if (!q.trim() && !token) return;
      setSearchError(null);
      if (append) setLoadingMore(true);
      else setSearchLoading(true);
      try {
        const body: ShoppingQueryRequest = {
          query: q,
          category: category === 'all' ? null : category,
          currency: 'USD',
          max_results: pageSize,
        };
        if (token) body.page_token = token;
        const data = await getAssistantRecommendations(body);
        const mapped = (data.search_results || []).map(mapChannel3Result);
        setOffers((prev) => (append ? [...prev, ...mapped] : mapped));
        setNextPageToken(data.next_page_token ?? null);
        setHasMore(!!(data.next_page_token || data.has_more));
        setHasSearched(true);
      } catch (err: any) {
        setSearchError(err.message || 'Unable to load products. Please try again.');
      } finally {
        setSearchLoading(false);
        setLoadingMore(false);
      }
    },
    [category, pageSize]
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      handleSearch(query.trim());
    },
    [query, handleSearch]
  );

  const handleLoadMore = useCallback(() => {
    if (hasMore && nextPageToken && !loadingMore) {
      handleSearch(query.trim(), nextPageToken, true);
    }
  }, [query, hasMore, nextPageToken, loadingMore, handleSearch]);

  const toggleCompare = useCallback((offer: ProductOffer) => {
    const next = new Set(compareRef.current);
    if (next.has(offer.id)) next.delete(offer.id);
    else if (next.size < 3) next.add(offer.id);
    compareRef.current = next;
  }, []);

  const isCompared = useCallback((id: string) => compareRef.current.has(id), []);

  const openInAssistant = useCallback(
    (offer: ProductOffer) => {
      onNavigate('assistant-chat', {
        intent: 'product',
        query: offer.title,
        product: offer,
      });
    },
    [onNavigate]
  );

  if (searchLoading && offers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-3">
        <span className="material-symbols-outlined text-accent text-xl animate-pulse">search</span>
        <span className="font-body-sm text-sm text-ink-muted">Searching product catalog…</span>
      </div>
    );
  }

  const displayOffers = hasSearched ? filtered : offers;

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <div>
          <h1 className="font-headline-md text-ink">Product Search</h1>
          <p className="font-body-sm text-sm text-ink-muted">
            Search verified merchant offers. All prices and details come from the
            live product catalog — no simulated data.
          </p>
        </div>
      </div>

      {/* Search & filters */}
      <div className="ps-card p-4">
        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
          <div className="md:col-span-5">
            <label className="ps-label">Search</label>
            <input
              className="ps-input"
              placeholder="Search by vendor, SKU, or specification…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="ps-label">Category</label>
            <select
              className="ps-input-sm"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.charAt(0).toUpperCase() + c.slice(1)}
                </option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="ps-label">Verification</label>
            <select
              className="ps-input-sm"
              value={verifiedOnly ? 'verified' : 'all'}
              onChange={(e) => setVerifiedOnly(e.target.value === 'verified')}
            >
              <option value="all">All merchants</option>
              <option value="verified">Price verified only</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="ps-label">Sort</label>
            <select
              className="ps-input-sm"
              value={sort}
              onChange={(e) => setSort(e.target.value)}
            >
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="md:col-span-1">
            <button type="submit" className="ps-btn ps-btn-primary w-full">
              Search
            </button>
          </div>
        </form>
        {searchError && (
          <div className="mt-3 p-3 rounded-md bg-block/10 border border-block/30 text-block text-sm font-medium">
            {searchError}
          </div>
        )}
      </div>

      {/* Results */}
      <div className="flex flex-col lg:flex-row gap-6">
        <div className="flex-1 lg:w-3/4">
          <div className="flex items-center gap-2 mb-3">
            <h2 className="font-headline-sm text-lg text-ink font-semibold">
              Results
            </h2>
            <span className="font-label-xs text-[10px] text-ink-muted">
              {displayOffers.length} offer{displayOffers.length !== 1 ? 's' : ''}
              {hasMore ? ' · more available' : ''}
            </span>
          </div>

          {searchError && offers.length === 0 && !searchLoading && (
            <div className="rounded-lg p-3 bg-block/10 border border-block/30 text-block text-sm">
              {searchError}
            </div>
          )}

          {!hasSearched && offers.length === 0 && (
            <EmptyState
              icon="manage_search"
              title="Search for products"
              description="Enter a search above to browse live merchant offers from the product catalog."
            />
          )}

          {hasSearched && displayOffers.length === 0 && (
            <EmptyState
              icon="search_off"
              title="No matching offers"
              description="Try adjusting your search terms, category, or verification filter."
            />
          )}

          {hasSearched && displayOffers.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {displayOffers.map((offer) => (
                <div key={offer.id} className="ps-card p-4 hover:border-border-hover transition-colors">
                  <div className="aspect-[4/3] w-full rounded-lg border border-border overflow-hidden mb-3 bg-surface">
                    {offer.imageUrl ? (
                      <img
                        src={offer.imageUrl}
                        alt={offer.title}
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-ink-light">
                        <span className="material-symbols-outlined text-xl">image</span>
                      </div>
                    )}
                  </div>
                  <p className="font-body-sm text-sm text-ink line-clamp-2 mb-1">{offer.title}</p>
                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="font-headline-sm text-lg font-tabular text-ink font-semibold">
                      {formatAmount(offer.price, offer.currency)}
                    </span>
                    {offer.price > 5000 && (
                      <span className="font-label-xs text-[10px] text-block">
                        Exceeds $5,000 ceiling
                      </span>
                    )}
                  </div>
                  <p className="font-body-xs text-xs text-ink-muted truncate mb-2">
                    {offer.merchantName} · {offer.merchantDomain}
                  </p>
                  <div className="flex items-center gap-2 mb-3">
                    <span
                      className={`ps-badge ${
                        offer.verification === 'VERIFIED_MERCHANT'
                          ? 'ps-badge-allow'
                          : 'ps-badge-review'
                      }`}
                    >
                      {offer.verification === 'VERIFIED_MERCHANT'
                        ? 'Price verified'
                        : 'Price unverified'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => toggleCompare(offer)}
                      className="ps-btn ps-btn-ghost flex-1 text-xs"
                    >
                      {isCompared(offer.id) ? 'Compared' : 'Compare'}
                    </button>
                    {offer.merchantUrl && (
                      <a
                        href={offer.merchantUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ps-btn ps-btn-ghost text-xs flex-1"
                      >
                        View on merchant site
                      </a>
                    )}
                    <button
                      type="button"
                      onClick={() => openInAssistant(offer)}
                      className="ps-btn ps-btn-primary text-xs flex-1"
                    >
                      Open in AI Assistant
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {hasMore && !searchLoading && !loadingMore && (
            <button
              type="button"
              onClick={handleLoadMore}
              className="ps-btn ps-btn-ghost w-full text-xs"
            >
              Load more
            </button>
          )}
          {loadingMore && (
            <p className="font-body-xs text-xs text-ink-muted text-center py-2">Loading more…</p>
          )}
        </div>

        {/* Comparison panel */}
        {compare.length > 0 && (
          <aside className="lg:w-1/4 flex-shrink-0">
            <div className="ps-card p-4 sticky top-6">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-headline-sm text-lg text-ink font-semibold">
                  Compare ({compare.length}/3)
                </h2>
                <button
                  type="button"
                  onClick={() => (compareRef.current = new Set())}
                  className="ps-btn ps-btn-danger text-xs"
                >
                  Clear
                </button>
              </div>
              <div className="space-y-3">
                {compare.map((offer) => (
                  <div key={offer.id} className="flex gap-3">
                    <div className="shrink-0 w-12 h-12 rounded-md border border-border overflow-hidden bg-surface flex items-center justify-center">
                      {offer.imageUrl ? (
                        <img src={offer.imageUrl} alt={offer.title} className="w-full h-full object-cover" loading="lazy" />
                      ) : (
                        <span className="material-symbols-outlined text-[11px] text-ink-light">image</span>
                      )}
                    </div>
                    <div className="flex-1">
                      <p className="font-body-xs text-xs text-ink line-clamp-1">{offer.title}</p>
                      <p className="font-tabular text-xs font-semibold text-ink">
                        {formatAmount(offer.price, offer.currency)}
                      </p>
                      <p className="font-label-xs text-[10px] text-ink-light truncate">
                        {offer.merchantName}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
};
