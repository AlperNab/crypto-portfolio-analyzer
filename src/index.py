#!/usr/bin/env python3
"""
crypto-portfolio-analyzer — wallet address or CSV → P&L, tax lots,
unrealized gains, DeFi position breakdown, risk analysis, cost basis
"""
import anthropic, json, re, sys
from pathlib import Path

SYSTEM = """You are a crypto tax accountant and portfolio analyst (CPA specializing in digital assets).
Analyze this crypto portfolio data.

IMPORTANT: This is for informational purposes only. Crypto tax rules vary by jurisdiction.
Always recommend consulting a qualified tax professional for actual tax filing.

Return ONLY valid JSON — no markdown, no explanation.

{
  "portfolio_summary": {
    "total_value_usd": number_or_null,
    "total_cost_basis_usd": number_or_null,
    "unrealized_pnl_usd": number_or_null,
    "unrealized_pnl_pct": number_or_null,
    "realized_pnl_ytd_usd": number_or_null,
    "assets_count": number,
    "reporting_date": "YYYY-MM-DD or null"
  },
  "holdings": [
    {
      "asset": "BTC|ETH|string",
      "quantity": number,
      "avg_cost_basis_usd": number_or_null,
      "current_price_usd": number_or_null,
      "current_value_usd": number_or_null,
      "unrealized_pnl_usd": number_or_null,
      "unrealized_pnl_pct": number_or_null,
      "pct_of_portfolio": number_or_null,
      "holding_period": "short_term_under_1yr|long_term_over_1yr|mixed|unknown"
    }
  ],
  "tax_lots": [
    {
      "asset": "string",
      "quantity": number,
      "acquisition_date": "YYYY-MM-DD or null",
      "cost_basis_usd": number,
      "current_value_usd": number_or_null,
      "unrealized_gain_loss": number_or_null,
      "holding_period": "short|long|unknown",
      "lot_id": "string or null"
    }
  ],
  "realized_transactions": [
    {
      "date": "YYYY-MM-DD",
      "type": "sale|swap|earn|airdrop|mining|staking|gift",
      "asset": "string",
      "quantity": number,
      "proceeds_usd": number,
      "cost_basis_usd": number,
      "gain_loss_usd": number,
      "holding_period": "short|long",
      "taxable": true_or_false
    }
  ],
  "defi_positions": [
    {
      "protocol": "Uniswap|Aave|Compound|string",
      "position_type": "liquidity_pool|lending|borrowing|staking|yield_farming",
      "assets": ["list of assets in position"],
      "value_usd": number_or_null,
      "apy_pct": number_or_null,
      "impermanent_loss_pct": number_or_null,
      "notes": "string"
    }
  ],
  "risk_analysis": {
    "concentration_risk": "BTC dominance too high|well_diversified|ETH heavy|altcoin_heavy",
    "top_holding_pct": number_or_null,
    "correlation_risk": "high|medium|low",
    "stablecoin_pct": number_or_null,
    "defi_exposure_pct": number_or_null,
    "warnings": ["specific risk warnings"]
  },
  "tax_planning": {
    "short_term_gains_usd": number_or_null,
    "long_term_gains_usd": number_or_null,
    "harvestable_losses_usd": number_or_null,
    "wash_sale_risk": "crypto_wash_sale_rules_vary_by_jurisdiction",
    "tax_optimization_opportunities": ["tax-loss harvesting candidates","long-term holds near 1yr mark"],
    "jurisdiction_notes": "tax rules vary — this is educational only"
  },
  "cost_basis_method": "FIFO|LIFO|HIFO|specific_identification|unknown",
  "data_quality": {
    "missing_cost_basis": ["assets with unknown cost basis"],
    "data_gaps": ["periods or transactions that couldn't be analyzed"],
    "confidence": "high|medium|low"
  },
  "disclaimer": "This analysis is for informational purposes only. Consult a qualified crypto tax professional for tax filing.",
  "confidence": 0.0
}"""

def analyze(portfolio_source: str, cost_basis_method: str = "FIFO") -> dict:
    client = anthropic.Anthropic()
    path = Path(portfolio_source)
    text = path.read_text(encoding="utf-8",errors="replace")[:30000] if path.exists() else portfolio_source[:30000]
    prompt = f"Cost basis method: {cost_basis_method}\n\nPortfolio data:\n{text}"
    resp = client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=3000, system=SYSTEM,
        messages=[{"role":"user","content":f"Analyze crypto portfolio:\n\n{prompt}"}]
    )
    raw = re.sub(r'^```(?:json)?\s*','',resp.content[0].text.strip(),flags=re.MULTILINE)
    raw = re.sub(r'\s*```$','',raw,flags=re.MULTILINE)
    return json.loads(raw)

def print_report(r: dict):
    s = r.get("portfolio_summary",{})
    risk = r.get("risk_analysis",{})
    tax = r.get("tax_planning",{})
    holdings = r.get("holdings",[])

    def fmt(v, prefix="$"):
        if v is None: return "N/A"
        return f"{prefix}{v:,.2f}" if prefix else f"{v:,.2f}"

    print(f"\n{'═'*60}")
    print(f"  CRYPTO PORTFOLIO ANALYZER")
    print(f"  Total value: {fmt(s.get('total_value_usd'))}")
    pnl = s.get("unrealized_pnl_usd",0) or 0
    pnl_pct = s.get("unrealized_pnl_pct",0) or 0
    pnl_arrow = "📈" if pnl >= 0 else "📉"
    print(f"  Unrealized P&L: {pnl_arrow} {fmt(pnl)} ({pnl_pct:+.1f}%)")
    if s.get("realized_pnl_ytd_usd") is not None: print(f"  Realized YTD: {fmt(s['realized_pnl_ytd_usd'])}")
    print(f"{'═'*60}")

    if holdings:
        print(f"\n  HOLDINGS ({len(holdings)})")
        sorted_h = sorted(holdings, key=lambda x: x.get("current_value_usd") or 0, reverse=True)
        for h in sorted_h[:8]:
            pct = h.get("pct_of_portfolio",0) or 0
            upnl = h.get("unrealized_pnl_usd",0) or 0
            upnl_pct = h.get("unrealized_pnl_pct",0) or 0
            bar = "█" * int(pct/5) + "░" * (20-int(pct/5))
            arrow = "+" if upnl >= 0 else ""
            print(f"  {h.get('asset','?'):<8} {fmt(h.get('current_value_usd'))} ({pct:.1f}%)  {arrow}{fmt(upnl)} ({upnl_pct:+.1f}%)")

    defi = r.get("defi_positions",[])
    if defi:
        print(f"\n  DEFI POSITIONS")
        for pos in defi:
            print(f"  {pos.get('protocol','?'):<20} {pos.get('position_type','?'):<20} {fmt(pos.get('value_usd'))}")
            if pos.get("impermanent_loss_pct"): print(f"     IL: {pos['impermanent_loss_pct']:.1f}%")

    print(f"\n  RISK")
    print(f"  {risk.get('concentration_risk','?')}")
    for w in risk.get("warnings",[]): print(f"  ⚠ {w}")

    if tax.get("short_term_gains_usd") is not None or tax.get("long_term_gains_usd") is not None:
        print(f"\n  TAX (informational)")
        if tax.get("short_term_gains_usd") is not None: print(f"  Short-term gains: {fmt(tax['short_term_gains_usd'])}")
        if tax.get("long_term_gains_usd") is not None: print(f"  Long-term gains:  {fmt(tax['long_term_gains_usd'])}")
        if tax.get("harvestable_losses_usd"): print(f"  Harvestable losses: {fmt(tax['harvestable_losses_usd'])}")
        opps = tax.get("tax_optimization_opportunities",[])
        if opps:
            for opp in opps[:2]: print(f"  💡 {opp}")

    print(f"\n  ⚠ {r.get('disclaimer','')}")
    print(f"  Confidence: {int(r.get('confidence',0)*100)}%")
    print(f"{'═'*60}\n")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Analyze crypto portfolio for P&L and tax lots")
    p.add_argument("source", help="Portfolio CSV, transaction history, or text description")
    p.add_argument("--method","-m",default="FIFO",choices=["FIFO","LIFO","HIFO"])
    p.add_argument("--json",action="store_true")
    a = p.parse_args()
    r = analyze(a.source, a.method)
    if a.json: print(json.dumps(r,indent=2,ensure_ascii=False))
    else: print_report(r)
