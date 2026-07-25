# PATCH Stop Qty Increase Blocked (2026-06-23)

## Scenario

Want to add to an existing position (UNH) to fill a pharma sector gap. The position has an existing Alpaca stop sell order (qty=5). Direct buy is blocked by wash trade 403.

## Attempted Workarounds

### 1. PATCH stop qty 5→13 (FAILED)
```python
r = requests.patch(f'{base}/v2/orders/{stop_id}',
    headers=headers, json={'qty': 13}, timeout=15)
# → 403: {"code":40310000,"available":"5","existing_qty":"5",
#         "message":"insufficient qty available"}
```

**Root cause**: Alpaca enforces that stop order qty cannot exceed current position qty. Even if the intent is "buy more and protect the combined position", the PATCH is rejected because you don't yet hold the planned new shares.

### 2. Direct market buy (FAILED)
```python
r = requests.post(f'{base}/v2/orders', headers=headers, json={
    'symbol': 'UNH', 'qty': 8, 'side': 'buy',
    'type': 'market', 'time_in_force': 'day'
}, timeout=15)
# → 403: {"code":40310000,"message":"potential wash trade detected",
#         "reject_reason":"opposite side market/stop order exists"}
```

### 3. Cancel stop then buy (NOT ATTEMPTED — deadlock risk)
Cancel → pending_cancel locks the position until next market open.

## Contrast with Known Patterns

| Operation | PATCH qty direction | Result | Documented |
|-----------|-------------------|--------|------------|
| TP sell (reduce position) | qty N→M (decrease) | ✅ 200 OK | Yes (§止盈卖出+止损单冲突) |
| Full exit (leave 1 share) | qty N→1 (decrease) | ✅ 200 OK | Yes (§全仓卖出+止损单冲突) |
| Full exit (PATCH qty=0) | qty N→0 | ❌ 400 qty must be > 0 | Yes (§全仓卖出+止损单冲突) |
| **Add to position** | **qty N→N+M (increase)** | **❌ 403 insufficient qty** | **This session** |

## Resolution

Since no workaround exists at the Alpaca API level:
- **Best path**: Wait for the stop to trigger (the position gets sold and the stop order disappears), then buy back
- **Alternative**: Choose a different stock in the same gap sector (if available)
- **Not recommended**: Cancel the stop order (pending_cancel deadlock)

## Related

- Skill §"已有持仓加仓 = Wash Trade 陷阱" (2026-06-08)
- Skill §"PATCH qty=0 被拒" (2026-06-16)
