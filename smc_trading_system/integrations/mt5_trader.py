# integrations/mt5_trader.py
# ─────────────────────────────────────────────────────────────────────────────
# LIVE TRADING EXECUTOR
# ─────────────────────────────────────────────────────────────────────────────
# Manages order placement, position management, and trade monitoring on MT5
# ─────────────────────────────────────────────────────────────────────────────

import MetaTrader5 as mt5
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass

from core.state import TradeSignal
from integrations.mt5_connector import MT5Connector


@dataclass
class OrderResult:
    """Result of an order operation."""
    success: bool
    order_id: Optional[int] = None
    ticket: Optional[int] = None
    error: Optional[str] = None
    comment: str = ""


@dataclass
class PositionInfo:
    """Current position information from MT5."""
    ticket: int
    symbol: str
    direction: str  # "BUY" or "SELL"
    volume: float
    open_price: float
    open_time: datetime
    current_price: float
    profit: float
    profit_pct: float
    sl: float
    tp: float


class MT5Trader:
    """
    Executes trades on MT5 based on signals from the SMC system.
    Manages position sizing, SL/TP placement, and trade monitoring.
    """

    def __init__(self, connector: MT5Connector, symbol: str, magic_number: int = 123456):
        """
        Initialize live trader.

        Args:
            connector: MT5Connector instance (must be connected)
            symbol: Trading pair (e.g., "EURUSD")
            magic_number: Unique identifier for trades placed by this system
        """
        self.connector = connector
        self.symbol = symbol
        self.magic_number = magic_number
        self.active_positions: Dict[int, PositionInfo] = {}

    def place_buy_order(
        self,
        signal: TradeSignal,
        volume: float,
        comment: str = "",
    ) -> OrderResult:
        """
        Place a BUY limit order with SL and TP.

        Args:
            signal: TradeSignal with entry_price, stop_loss, take_profit
            volume: Lot size
            comment: Order comment

        Returns:
            OrderResult with success status and order details
        """
        if not self.connector.connected:
            return OrderResult(success=False, error="Not connected to MT5")

        try:
            # Prepare request
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": self.symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_BUY_LIMIT,
                "price": signal.entry_price,
                "stoploss": signal.stop_loss,
                "takeprofit": signal.take_profit,
                "deviation": 5,
                "magic": self.magic_number,
                "comment": comment or f"SMC Entry #{signal.reason}",
                "type_time": mt5.ORDER_TIME_GTC,  # Good till cancel
                "type_filling": mt5.ORDER_FILLING_IOC,  # Immediate or cancel
            }

            # Send order
            result = mt5.order_send(request)

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                error_msg = f"Order failed: {result.comment} (code {result.retcode})"
                print(f"[MT5 Trader] {error_msg}")
                return OrderResult(success=False, error=error_msg)

            print(f"[MT5 Trader] BUY order placed: {result.order} | "
                  f"Volume: {volume} | Entry: {signal.entry_price} | "
                  f"SL: {signal.stop_loss} | TP: {signal.take_profit}")

            return OrderResult(
                success=True,
                order_id=result.order,
                ticket=result.deal,
                comment=f"Order {result.order}"
            )

        except Exception as e:
            error_msg = f"Buy order error: {e}"
            print(f"[MT5 Trader] {error_msg}")
            return OrderResult(success=False, error=error_msg)

    def place_sell_order(
        self,
        signal: TradeSignal,
        volume: float,
        comment: str = "",
    ) -> OrderResult:
        """
        Place a SELL limit order with SL and TP.

        Args:
            signal: TradeSignal with entry_price, stop_loss, take_profit
            volume: Lot size
            comment: Order comment

        Returns:
            OrderResult with success status and order details
        """
        if not self.connector.connected:
            return OrderResult(success=False, error="Not connected to MT5")

        try:
            # Prepare request
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": self.symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_SELL_LIMIT,
                "price": signal.entry_price,
                "stoploss": signal.stop_loss,
                "takeprofit": signal.take_profit,
                "deviation": 5,
                "magic": self.magic_number,
                "comment": comment or f"SMC Entry #{signal.reason}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            # Send order
            result = mt5.order_send(request)

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                error_msg = f"Order failed: {result.comment} (code {result.retcode})"
                print(f"[MT5 Trader] {error_msg}")
                return OrderResult(success=False, error=error_msg)

            print(f"[MT5 Trader] SELL order placed: {result.order} | "
                  f"Volume: {volume} | Entry: {signal.entry_price} | "
                  f"SL: {signal.stop_loss} | TP: {signal.take_profit}")

            return OrderResult(
                success=True,
                order_id=result.order,
                ticket=result.deal,
                comment=f"Order {result.order}"
            )

        except Exception as e:
            error_msg = f"Sell order error: {e}"
            print(f"[MT5 Trader] {error_msg}")
            return OrderResult(success=False, error=error_msg)

    def close_position(self, ticket: int, comment: str = "") -> OrderResult:
        """
        Close an open position.

        Args:
            ticket: Position ticket number
            comment: Close comment

        Returns:
            OrderResult with success status
        """
        if not self.connector.connected:
            return OrderResult(success=False, error="Not connected to MT5")

        try:
            # Get position details
            pos = mt5.positions_get(ticket=ticket)
            if pos is None or len(pos) == 0:
                return OrderResult(success=False, error=f"Position {ticket} not found")

            position = pos[0]
            volume = position.volume
            order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY

            # Prepare close request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": position.symbol,
                "volume": volume,
                "type": order_type,
                "position": ticket,
                "magic": self.magic_number,
                "comment": comment or f"SMC Close #{ticket}",
                "type_time": mt5.ORDER_TIME_IOC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            # Send close request
            result = mt5.order_send(request)

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                error_msg = f"Close failed: {result.comment} (code {result.retcode})"
                print(f"[MT5 Trader] {error_msg}")
                return OrderResult(success=False, error=error_msg)

            print(f"[MT5 Trader] Position {ticket} closed | Profit: {position.profit:,.2f}")
            return OrderResult(success=True, comment=f"Closed {volume} lots")

        except Exception as e:
            error_msg = f"Close position error: {e}"
            print(f"[MT5 Trader] {error_msg}")
            return OrderResult(success=False, error=error_msg)

    def modify_position(
        self,
        ticket: int,
        new_sl: Optional[float] = None,
        new_tp: Optional[float] = None,
    ) -> OrderResult:
        """
        Modify stop loss and/or take profit of an open position.

        Args:
            ticket: Position ticket number
            new_sl: New stop loss price (or None to keep current)
            new_tp: New take profit price (or None to keep current)

        Returns:
            OrderResult with success status
        """
        if not self.connector.connected:
            return OrderResult(success=False, error="Not connected to MT5")

        try:
            # Get position details
            pos = mt5.positions_get(ticket=ticket)
            if pos is None or len(pos) == 0:
                return OrderResult(success=False, error=f"Position {ticket} not found")

            position = pos[0]

            # Use current values if not specified
            if new_sl is None:
                new_sl = position.sl
            if new_tp is None:
                new_tp = position.tp

            # Prepare modify request
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": position.symbol,
                "position": ticket,
                "sl": new_sl,
                "tp": new_tp,
                "magic": self.magic_number,
                "comment": f"SMC Modify SL/TP",
            }

            # Send modify request
            result = mt5.order_send(request)

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                error_msg = f"Modify failed: {result.comment} (code {result.retcode})"
                print(f"[MT5 Trader] {error_msg}")
                return OrderResult(success=False, error=error_msg)

            print(f"[MT5 Trader] Position {ticket} modified | SL: {new_sl} | TP: {new_tp}")
            return OrderResult(success=True)

        except Exception as e:
            error_msg = f"Modify position error: {e}"
            print(f"[MT5 Trader] {error_msg}")
            return OrderResult(success=False, error=error_msg)

    def get_positions(self) -> List[PositionInfo]:
        """
        Get all open positions with magic number matching this system.

        Returns:
            List of PositionInfo objects
        """
        if not self.connector.connected:
            return []

        try:
            positions = mt5.positions_get(symbol=self.symbol)
            if positions is None:
                return []

            result = []
            for pos in positions:
                if pos.magic != self.magic_number:
                    continue  # Skip positions from other systems

                symbol_info = self.connector.get_symbol_info(pos.symbol)
                current_price = symbol_info.get("bid" if pos.type == mt5.POSITION_TYPE_BUY else "ask") if symbol_info else 0

                profit_pct = 0
                if current_price:
                    if pos.type == mt5.POSITION_TYPE_BUY:
                        profit_pct = ((current_price - pos.price_open) / pos.price_open) * 100
                    else:
                        profit_pct = ((pos.price_open - current_price) / pos.price_open) * 100

                position_info = PositionInfo(
                    ticket=pos.ticket,
                    symbol=pos.symbol,
                    direction="BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                    volume=pos.volume,
                    open_price=pos.price_open,
                    open_time=datetime.fromtimestamp(pos.time),
                    current_price=current_price,
                    profit=pos.profit,
                    profit_pct=profit_pct,
                    sl=pos.sl,
                    tp=pos.tp,
                )
                result.append(position_info)

            return result

        except Exception as e:
            print(f"[MT5 Trader] Error fetching positions: {e}")
            return []

    def cancel_order(self, order_id: int) -> OrderResult:
        """
        Cancel a pending order.

        Args:
            order_id: Order ticket number

        Returns:
            OrderResult with success status
        """
        if not self.connector.connected:
            return OrderResult(success=False, error="Not connected to MT5")

        try:
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": order_id,
                "magic": self.magic_number,
                "comment": "SMC Cancel Order",
            }

            result = mt5.order_send(request)

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                error_msg = f"Cancel failed: {result.comment} (code {result.retcode})"
                print(f"[MT5 Trader] {error_msg}")
                return OrderResult(success=False, error=error_msg)

            print(f"[MT5 Trader] Order {order_id} cancelled")
            return OrderResult(success=True)

        except Exception as e:
            error_msg = f"Cancel order error: {e}"
            print(f"[MT5 Trader] {error_msg}")
            return OrderResult(success=False, error=error_msg)
