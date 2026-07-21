"""
execution/ — 交易执行层 (V7.1 Phase 3)

Breakdown of us_trader.py (1674 lines) into 5 single-responsibility modules:

  trade_executor.py    — Orchestration: risk, events, buy logic, report/execute/stops modes, CLI
  position_manager.py  — State + data + analysis: load/save state, get_bars, analyze, tech_snapshot
  order_manager.py     — Order CRUD through AlpacaClient: place, cancel, dedupe, replacement tracking
  stop_loss_manager.py — Dual-layer stop loss: trail stops, coverage audit, ghost detection, blacklist
  take_profit_manager.py — Tiered exits: RSI > 80 sell 50%, drawdown sell all

All orders pass through: OrderIntent → Safety Check (trading_lock + degraded_mode) → OrderStateMachine → Broker.
No direct Alpaca API calls — all routed through broker/alpaca_client.py.
"""

from eagle_eye.execution.order_intent import OrderIntent, OrderSide, OrderType, OrderIntentStatus
from eagle_eye.execution.order_state_machine import OrderStateMachine, OrderState, OrderRecord, get_order_state_machine
from eagle_eye.execution.position_manager import (
    load_state, save_state, get_highest, set_highest, get_trail_stop,
    get_sector, get_bars, analyze, tech_snapshot,
)
from eagle_eye.execution.order_manager import (
    get_portfolio, get_holdings, get_open_stop_orders, get_open_buy_orders,
    place_market_order, place_stop_order, cancel_order,
    log_sell_for_replacement, check_pending_replacements, clear_pending_replacement,
)
from eagle_eye.execution.stop_loss_manager import (
    update_trail_stops, stop_coverage_audit, detect_ghost_stops, update_stop_blacklist,
)
from eagle_eye.execution.take_profit_manager import execute_take_profit
from eagle_eye.execution.trade_executor import (
    main, report_mode, execute_mode, stops_mode, run_cli,
    check_account_risk, check_position_utilization,
)
from eagle_eye.execution.candidate_tracker import (
    record_scan, get_consecutive_count, get_eligible_seeds,
)

__all__ = [
    # Order flow
    'OrderIntent', 'OrderSide', 'OrderType', 'OrderIntentStatus',
    'OrderStateMachine', 'OrderState', 'OrderRecord', 'get_order_state_machine',
    # Position & analysis
    'load_state', 'save_state', 'get_highest', 'set_highest', 'get_trail_stop',
    'get_sector', 'get_bars', 'analyze', 'tech_snapshot',
    # Order management
    'get_portfolio', 'get_holdings', 'get_open_stop_orders', 'get_open_buy_orders',
    'place_market_order', 'place_stop_order', 'cancel_order',
    'log_sell_for_replacement', 'check_pending_replacements', 'clear_pending_replacement',
    # Stop loss & take profit
    'update_trail_stops', 'stop_coverage_audit', 'detect_ghost_stops', 'update_stop_blacklist',
    'execute_take_profit',
    # Orchestration
    'main', 'report_mode', 'execute_mode', 'stops_mode', 'run_cli',
    'check_account_risk', 'check_position_utilization',
    # Candidate tracking (P0)
    'record_scan', 'get_consecutive_count', 'get_eligible_seeds',
]
