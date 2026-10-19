"""Three-product recommendation engine curating Top Value, Best Performance,
and Budget Champion recommendations with evidence-based scoring.
"""

from typing import List, Optional
from backend.assistant.catalog import get_catalog_products
from backend.assistant.models import (
    ProductItem,
    ProductRecommendation,
    ShoppingIntent,
)
from backend.assistant.scoring import ScoringEngine


class RecommendationEngine:
    """Ranks and curates exactly three products matching user intent."""

    def __init__(self, scoring_engine: Optional[ScoringEngine] = None):
        self.scoring = scoring_engine or ScoringEngine()

    def get_three_recommendations(
        self, intent: ShoppingIntent, preferred_merchant: Optional[str] = None
    ) -> List[ProductRecommendation]:
        # 1. Fetch products for category
        products = get_catalog_products(intent.category)

        # If preferred merchant provided, prioritize
        if preferred_merchant and preferred_merchant.strip():
            merchant_filter = preferred_merchant.lower().strip()
            filtered = [p for p in products if merchant_filter in p.merchant_name.lower()]
            if len(filtered) >= 3:
                products = filtered

        # 2. Score all candidate products with PVS and WTS
        scored_items = []
        for p in products:
            pvs = self.scoring.calculate_product_value_score(p, intent)
            wts = self.scoring.calculate_website_trust_score(p)
            combined_score = 0.65 * pvs.overall_score + 0.35 * wts.overall_trust
            scored_items.append({
                "product": p,
                "pvs": pvs,
                "wts": wts,
                "combined": combined_score,
            })

        if not scored_items:
            return []

        # 3. Partition and select 3 distinct archetypes:
        # Sort by combined score descending
        by_score = sorted(scored_items, key=lambda x: x["combined"], reverse=True)
        # Sort by price ascending (for Budget Champion)
        by_price = sorted(scored_items, key=lambda x: x["product"].price)
        # Sort by rating / spec / highest tier (for Best Performance)
        by_performance = sorted(
            scored_items,
            key=lambda x: (x["product"].rating, x["pvs"].specification_match_score, x["product"].price),
            reverse=True,
        )

        selected_ids = set()
        chosen: List[dict] = []

        # Pick Rank 1: Top Value Pick (highest combined PVS + WTS)
        top_val = by_score[0]
        chosen.append({**top_val, "rank": 1, "badge": "Top Value Pick"})
        selected_ids.add(top_val["product"].id)

        # Pick Rank 2: Best Performance (highest spec/quality not yet picked)
        perf_candidate = next((x for x in by_performance if x["product"].id not in selected_ids), None)
        if not perf_candidate:
            perf_candidate = next((x for x in by_score if x["product"].id not in selected_ids), by_score[0])
        chosen.append({**perf_candidate, "rank": 2, "badge": "Best Performance"})
        selected_ids.add(perf_candidate["product"].id)

        # Pick Rank 3: Budget Champion (lowest price / high price-efficiency not yet picked)
        budget_candidate = next((x for x in by_price if x["product"].id not in selected_ids), None)
        if not budget_candidate:
            budget_candidate = next((x for x in by_score if x["product"].id not in selected_ids), by_score[0])
        chosen.append({**budget_candidate, "rank": 3, "badge": "Budget Champion"})
        selected_ids.add(budget_candidate["product"].id)

        # Build recommendation objects
        recommendations: List[ProductRecommendation] = []
        for item in chosen:
            p: ProductItem = item["product"]
            pvs = item["pvs"]
            wts = item["wts"]
            rank = item["rank"]
            badge = item["badge"]

            if badge == "Top Value Pick":
                why = (
                    f"Optimal balance of price (${p.price:.2f}), {p.rating}★ user satisfaction, "
                    f"and an evidence-based Product Value Score of {pvs.overall_score}/100."
                )
            elif badge == "Best Performance":
                why = (
                    f"Class-leading specifications and premium engineering from {p.brand}. "
                    f"Spec match score of {pvs.specification_match_score}/100 for demanding workflows."
                )
            else:
                why = (
                    f"Most cost-effective entry point at ${p.price:.2f}. Delivers essential capability "
                    f"with verified merchant trust ({wts.overall_trust}/100)."
                )

            recommendations.append(
                ProductRecommendation(
                    rank=rank,
                    badge=badge,
                    product=p,
                    value_score=pvs,
                    trust_score=wts,
                    why_recommended=why,
                )
            )

        return recommendations[:3]
