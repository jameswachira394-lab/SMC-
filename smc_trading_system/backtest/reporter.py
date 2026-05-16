# backtest/reporter.py
# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST REPORTER
# ─────────────────────────────────────────────────────────────────────────────
# Outputs:
#   • Win rate
#   • Expectancy (R)
#   • Max drawdown
#   • Drawdown curve
#   • RR distribution
#   • Trade frequency per session
#   • Full JSON report + CSV trades
# ─────────────────────────────────────────────────────────────────────────────
import json
import csv
import os
from typing import List, Dict, Any
from collections import defaultdict

from backtest.simulator import TradeRecord
from config.settings import ACCOUNT_SIZE


class BacktestReporter:

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(
        self,
        trades: List[TradeRecord],
        equity_curve: List[dict],
    ) -> Dict[str, Any]:
        """
        Compute all statistics and write output files.
        Returns the full report as a dict.
        """
        if not trades:
            print("[Reporter] No trades to report.")
            return {}

        report = {}

        # ── Basic stats ───────────────────────────────────────────────────────
        total      = len(trades)
        wins       = [t for t in trades if t.pnl_r > 0]
        losses     = [t for t in trades if t.pnl_r <= 0]
        win_rate   = len(wins) / total * 100
        avg_win    = sum(t.pnl_r for t in wins) / len(wins) if wins else 0
        avg_loss   = sum(t.pnl_r for t in losses) / len(losses) if losses else 0
        expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

        report["summary"] = {
            "total_trades":    total,
            "wins":            len(wins),
            "losses":          len(losses),
            "win_rate_pct":    round(win_rate, 2),
            "avg_win_r":       round(avg_win, 4),
            "avg_loss_r":      round(avg_loss, 4),
            "expectancy_r":    round(expectancy, 4),
            "total_r":         round(sum(t.pnl_r for t in trades), 4),
            "best_trade_r":    round(max(t.pnl_r for t in trades), 4),
            "worst_trade_r":   round(min(t.pnl_r for t in trades), 4),
            "profit_factor":   round(
                sum(t.pnl_r for t in wins) / abs(sum(t.pnl_r for t in losses))
                if losses and sum(t.pnl_r for t in losses) != 0 else float('inf'), 4
            ),
        }

        # ── Drawdown ──────────────────────────────────────────────────────────
        balances = [e["balance"] for e in equity_curve]
        peak = ACCOUNT_SIZE
        max_dd = 0.0
        dd_curve = []
        for b in balances:
            if b > peak:
                peak = b
            dd = (peak - b) / peak * 100 if peak > 0 else 0
            dd_curve.append(round(dd, 4))
            if dd > max_dd:
                max_dd = dd

        report["drawdown"] = {
            "max_drawdown_pct": round(max_dd, 2),
            "final_balance":    round(balances[-1], 2) if balances else ACCOUNT_SIZE,
            "net_pnl_pct":      round((balances[-1] - ACCOUNT_SIZE) / ACCOUNT_SIZE * 100, 2)
                                if balances else 0,
        }

        # ── RR Distribution ───────────────────────────────────────────────────
        rr_buckets: Dict[str, int] = defaultdict(int)
        for t in trades:
            if t.pnl_r <= -1.0:
                rr_buckets["-1R (SL)"] += 1
            elif t.pnl_r < 0:
                rr_buckets["<0R (partial loss)"] += 1
            elif t.pnl_r < 1.0:
                rr_buckets["0-1R"] += 1
            elif t.pnl_r < 2.0:
                rr_buckets["1-2R"] += 1
            elif t.pnl_r < 3.0:
                rr_buckets["2-3R"] += 1
            else:
                rr_buckets["3R+"] += 1
        report["rr_distribution"] = dict(rr_buckets)

        # ── Session breakdown ─────────────────────────────────────────────────
        session_stats: Dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "total_r": 0.0})
        for t in trades:
            s = t.session
            session_stats[s]["trades"] += 1
            session_stats[s]["total_r"] += t.pnl_r
            if t.pnl_r > 0:
                session_stats[s]["wins"] += 1
        for s, d in session_stats.items():
            d["win_rate_pct"] = round(d["wins"] / d["trades"] * 100, 1) if d["trades"] else 0
            d["total_r"] = round(d["total_r"], 4)
        report["session_breakdown"] = dict(session_stats)

        # ── Direction breakdown ───────────────────────────────────────────────
        longs  = [t for t in trades if t.direction == "long"]
        shorts = [t for t in trades if t.direction == "short"]
        report["direction_breakdown"] = {
            "longs": {
                "count": len(longs),
                "win_rate": round(len([t for t in longs if t.pnl_r > 0]) / len(longs) * 100, 1)
                            if longs else 0,
                "total_r": round(sum(t.pnl_r for t in longs), 4),
            },
            "shorts": {
                "count": len(shorts),
                "win_rate": round(len([t for t in shorts if t.pnl_r > 0]) / len(shorts) * 100, 1)
                            if shorts else 0,
                "total_r": round(sum(t.pnl_r for t in shorts), 4),
            },
        }

        # ── Consecutive stats ─────────────────────────────────────────────────
        max_consec_wins = max_consec_losses = 0
        cur_wins = cur_losses = 0
        for t in trades:
            if t.pnl_r > 0:
                cur_wins += 1
                cur_losses = 0
            else:
                cur_losses += 1
                cur_wins = 0
            max_consec_wins   = max(max_consec_wins, cur_wins)
            max_consec_losses = max(max_consec_losses, cur_losses)
        report["streaks"] = {
            "max_consecutive_wins":   max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
        }

        # ── Write files ───────────────────────────────────────────────────────
        report_path = os.path.join(self.output_dir, "backtest_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"[Reporter] Report saved: {report_path}")

        trades_path = os.path.join(self.output_dir, "trades.csv")
        if trades:
            with open(trades_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=trades[0].to_dict().keys())
                writer.writeheader()
                for t in trades:
                    writer.writerow(t.to_dict())
            print(f"[Reporter] Trades CSV saved: {trades_path}")

        equity_path = os.path.join(self.output_dir, "equity_curve.csv")
        if equity_curve:
            with open(equity_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=equity_curve[0].keys())
                writer.writeheader()
                writer.writerows(equity_curve)
            print(f"[Reporter] Equity curve saved: {equity_path}")

        # ── Console summary ───────────────────────────────────────────────────
        self._print_summary(report)

        return report

    def _print_summary(self, report: dict):
        s = report["summary"]
        d = report["drawdown"]
        print("\n" + "=" * 60)
        print("  SMC BACKTEST RESULTS")
        print("=" * 60)
        print(f"  Total Trades     : {s['total_trades']}")
        print(f"  Win Rate         : {s['win_rate_pct']}%")
        print(f"  Expectancy       : {s['expectancy_r']}R per trade")
        print(f"  Total R          : {s['total_r']}R")
        print(f"  Profit Factor    : {s['profit_factor']}")
        print(f"  Max Drawdown     : {d['max_drawdown_pct']}%")
        print(f"  Final Balance    : ${d['final_balance']:,.2f}")
        print(f"  Net P&L          : {d['net_pnl_pct']}%")
        print("-" * 60)
        print("  Session Breakdown:")
        for sess, stats in report["session_breakdown"].items():
            print(f"    {sess:<22} {stats['trades']:>3} trades | "
                  f"WR: {stats['win_rate_pct']}% | {stats['total_r']}R")
        print("-" * 60)
        print("  RR Distribution:")
        for bucket, count in report["rr_distribution"].items():
            print(f"    {bucket:<20} {count}")
        print("=" * 60 + "\n")
