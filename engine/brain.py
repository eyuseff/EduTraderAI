from __future__ import annotations

from dataclasses import dataclass, field

from audit.trade_log import AuditLog
from scanner_engine.automated_scanner import ScanResult, scan_market
from trading.execution import PaperExecutionEngine
from trading.risk_manager import TradeProposal


@dataclass
class TradingCycleReport:
    scan: ScanResult
    submitted: list[dict] = field(default_factory=list)
    rejected_by_risk: list[dict] = field(default_factory=list)


class EduTraderBrain:
    def __init__(self, execution: PaperExecutionEngine, audit_log: AuditLog | None = None) -> None:
        self.execution = execution
        self.audit = audit_log or AuditLog()

    def run_cycle(self, symbols: list[str], *, min_score: int = 80,
                  max_new_trades: int = 3, submit_orders: bool = False) -> TradingCycleReport:
        if not self.execution.broker.is_paper:
            raise RuntimeError("Automation is locked to paper brokers only.")
        scan = scan_market(symbols, min_score=min_score, max_candidates=max_new_trades * 3)
        report = TradingCycleReport(scan=scan)
        self.audit.write("scan_completed", {
            "scanned": scan.scanned,
            "qualified": len(scan.qualified),
            "regime": scan.regime.label,
            "regime_score": scan.regime.score,
            "submit_orders": submit_orders,
        })

        for signal in scan.qualified:
            if len(report.submitted) >= max_new_trades:
                break
            proposal = TradeProposal(
                symbol=signal.symbol,
                entry_price=signal.entry_price,
                stop_price=signal.stop_price,
                target_price=signal.target_price,
            )
            decision = self.execution.preview(proposal)
            if not decision.approved:
                row = {"symbol": signal.symbol, "reasons": decision.reasons}
                report.rejected_by_risk.append(row)
                self.audit.write("risk_rejected", row)
                continue
            if submit_orders:
                order = self.execution.submit(proposal, "PAPER TRADE")
                row = {"symbol": order.symbol, "quantity": order.quantity, "order_id": order.order_id}
                report.submitted.append(row)
                self.audit.write("paper_order_submitted", row)
            else:
                report.submitted.append({
                    "symbol": signal.symbol,
                    "quantity": decision.quantity,
                    "order_id": "PREVIEW_ONLY",
                })
        return report
