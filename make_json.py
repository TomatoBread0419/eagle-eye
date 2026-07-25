#!/usr/bin/env python3
import json

data = {
  "scan_time": "2026-06-26T04:06:00+08:00",
  "scan_time_utc": "2026-06-25T20:06:00Z",
  "sectors": [
    {
      "sector": "半导体/AI",
      "en": [
        {"title": "Taiwan Semiconductor (TSM) Sees AI Chip Demand Outpacing Supply", "source": "Yahoo Finance", "date": "2026-06-01"},
        {"title": "NVDA Gains 23.5% Since April, TSM Up 19.7%: What's Driving the Rally?", "source": "TradingView", "date": "2026-04-12"},
        {"title": "Prediction: The Best Pick-and-Shovel AI Stock of 2026 Won't Be Nvidia or Broadcom", "source": "The Motley Fool", "date": "2026-04-25"}
      ],
      "zh": [
        {"title": "苹果芯片战略历史性调整！跳过M6高端版本，直接布局以AI为核心的M7系列", "source": "wallstreetcn", "date": "2026-06-26", "snippet": "苹果跳过M6 Pro/Max高端版本，直接以AI为核心设计M7系列，最早2027年落地。M6基础版内存带宽跃升至200GB/s，GPU核心增至12个。同时苹果宣布Mac、iPad全线提价，最高涨300美元。股价单日重挫逾5%。"},
        {"title": "DeepSeek 开启【倍增】式扩招：剑指AI搜索与数据壁垒", "source": "wallstreetcn", "date": "2026-06-26", "snippet": "DeepSeek宣布将所有部门规模至少扩大一倍，广招服务端开发、预训练数据、AI搜索工程师。市场预计低成本AI模型的崛起将削弱对AI芯片的持续投入需求，英伟达股价盘中一度下跌3.5%。"},
        {"title": "千亿业绩目标背后，联想问天重押AI算力底座", "source": "wallstreetcn", "date": "2026-06-26"}
      ],
      "wsc": [
        {"title": "DeepSeek 开启【倍增】式扩招：剑指 AI 搜索与数据壁垒，大模型商业化决战打响", "source": "wallstreetcn", "date": "2026-06-26 04:01"},
        {"title": "苹果芯片战略历史性调整！跳过M6高端版本，直接布局以AI为核心的M7系列", "source": "wallstreetcn", "date": "2026-06-26 02:13"},
        {"title": "千亿业绩目标背后，联想问天重押AI算力底座", "source": "wallstreetcn", "date": "2026-06-26 01:24"}
      ]
    },
    {
      "sector": "地缘/台海",
      "en": [
        {"title": "Taiwan Strait Tensions Push Countries to Diversify Semiconductor Supply Chains", "source": "thehilltoponline.com", "date": "2026-05-14"},
        {"title": "Author: Chips made at Arizona's TSMC plant would be a lifeline if there's conflict with China", "source": "KJZZ", "date": "2026-03-13"},
        {"title": "The $10 Trillion Fight: Modeling a US-China War Over Taiwan", "source": "Bloomberg", "date": "2026-03-22"},
        {"title": "Geopolitical Tension Puts TSMC Valuation And Supply Chain Resilience In Focus", "source": "Yahoo Finance", "date": "2026-02-05"}
      ],
      "zh": [
        {"title": "霍尔木兹海峡再起波澜：伊朗被曝谋求一年400亿【买路钱】，船只遇袭后疏散行动暂停", "source": "wallstreetcn", "date": "2026-06-26", "snippet": "伊朗正游说中东等地区国家支持收海峡通行费计划，要与波斯湾周边国家分享收益。伊朗成立险企，要求经过海峡船只必须使用该司保险服务。鲁比奥称，任何国家无权对海峡收费。国际海事组织称一艘船周四在阿曼湾遭袭。"}
      ],
      "wsc": [
        {"title": "霍尔木兹海峡再起波澜：伊朗被曝谋求一年400亿【买路钱】，船只遇袭后疏散行动暂停", "source": "wallstreetcn", "date": "2026-06-26 03:18"}
      ]
    },
    {
      "sector": "美联储/货币政策",
      "en": [
        {"title": "Will New US Fed Chair Kevin Warsh Raise Interest Rates This Year?", "source": "Morningstar", "date": "2026-06-25"},
        {"title": "Fed Holds Rates and Leans Toward Fighting Inflation With Future Increases", "source": "The New York Times", "date": "2026-06-25"},
        {"title": "The Fed will bring down the hammer on inflation with a series of rate hikes this year, BofA says", "source": "Fortune", "date": "2026-06-23"},
        {"title": "Kevin Warsh faces first major test as Federal Reserve chair", "source": "Northeastern Global News", "date": "2026-06-17"},
        {"title": "Federal Reserve keeps rate unchanged, but nearly half of policymakers would support hike this year", "source": "OPB", "date": "2026-06-17"}
      ],
      "zh": [
        {"title": "央行重磅定调2026!降准降息将灵活落地", "source": "Sogou微信", "date": "2026-06月", "snippet": "央行明确适度宽松货币政策路线图，降准降息将灵活落地"},
        {"title": "盛松成: 为什么说现在降准比降息更重要?", "source": "Sogou微信", "date": "2026-06月"},
        {"title": "灵活高效降准降息,央行明确适度宽松货币政策路线图", "source": "Sogou微信", "date": "2026-06月"},
        {"title": "美联储三把手威廉姆斯：美国将在2028年实现通胀目标2%，届时失业率将回落至4%", "source": "wallstreetcn", "date": "2026-06-26", "snippet": "美联储三把手威廉姆斯称通胀目标2%要到2028年实现"}
      ],
      "wsc": [
        {"title": "美联储三把手威廉姆斯：美国将在2028年实现通胀目标2%，届时失业率将回落至4%", "source": "wallstreetcn", "date": "2026-06-26 03:43"}
      ]
    },
    {
      "sector": "贸易/访华",
      "en": [
        {"title": "Trump talks up trade deals with China, but experts see no big wins for U.S.", "source": "CBS News", "date": "2026-05-15"},
        {"title": "Trump Touts 'Fantastic Trade Deals' With China, but Details Are Scarce", "source": "The New York Times", "date": "2026-05-11"},
        {"title": "A trade boost and a new relationship status: U.S. touts modest China deals after summit's good vibes", "source": "NBC News", "date": "2026-05-15"}
      ],
      "zh": [],
      "wsc": []
    },
    {
      "sector": "原材料 (钨/稀土)",
      "en": [
        {"title": "[SMM Analysis] Brief Analysis of May Tungsten Import and Export Market", "source": "Shanghai Metals Market", "date": "2026-06-03"},
        {"title": "China's Tungsten Carbide and Powder Exports to Japan Reportedly Drop to Zero in Feb-Apr as Prices Surge", "source": "TrendForce", "date": "2026-05-21"},
        {"title": "China Tightens the Screws on Key Metals After Rare Earth Truce With Trump", "source": "OilPrice.com", "date": "2026-05-25"},
        {"title": "In tungsten territory, China celebrates control of mineral the U.S. needs", "source": "The Washington Post", "date": "2026-06-13"},
        {"title": "Rare-earths and tungsten: Pricing power, supply wars, and stock market implications", "source": "Stockhouse", "date": "2026-05-29"}
      ],
      "zh": [
        {"title": "A股突破下降通道，外资涌入加仓中国", "source": "Sogou微信", "date": "2026-06月"},
        {"title": "人民币升值重塑A股格局:受益板块与风险警示", "source": "Sogou微信", "date": "2026-06月"}
      ],
      "wsc": []
    }
  ],
  "market_data": {
    "US Indices": [
      {"name": "标普500", "code": ".INX", "price": "7357.50", "chg_pct": "🔴-0.01%", "date": "2026-06-25"},
      {"name": "道琼斯", "code": ".DJI", "price": "51920.62", "chg_pct": "🟢+0.14%", "date": "2026-06-25"},
      {"name": "纳斯达克", "code": ".IXIC", "price": "25358.60", "chg_pct": "🔴-0.46%", "date": "2026-06-25"},
      {"name": "VIX波动率", "code": ".VIX", "price": "21.67", "chg_pct": "🟡 中性(>20偏高)", "date": "2026-06-25"}
    ],
    "US Stocks": [
      {"name": "英伟达", "code": "NVDA", "price": "195.74", "chg_pct": "🔴-1.64%", "driver": "DeepSeek扩招->低成本AI模型冲击芯片需求叙事"},
      {"name": "苹果", "code": "AAPL", "price": "275.15", "chg_pct": "🔴-6.12%", "driver": "跳过M6 Pro/Max转向M7 AI芯片+全线提价$300"},
      {"name": "特斯拉", "code": "TSLA", "price": "375.12", "chg_pct": "🟡-0.11%", "driver": "基本持平"},
      {"name": "台积电", "code": "TSM", "price": "435.42", "chg_pct": "🔴-1.23%", "driver": "跟跌芯片板块"},
      {"name": "博通", "code": "AVGO", "price": "378.91", "chg_pct": "🔴-0.83%"},
      {"name": "微软", "code": "MSFT", "price": "352.83", "chg_pct": "🔴-3.46%"},
      {"name": "Meta", "code": "META", "price": "542.87", "chg_pct": "🔴-2.65%"},
      {"name": "亚马逊", "code": "AMZN", "price": "227.01", "chg_pct": "🔴-3.10%"},
      {"name": "谷歌-C", "code": "GOOG", "price": "342.19", "chg_pct": "🔴-0.83%"}
    ]
  },
  "summary": {
    "scan_timestamp": "2026-06-26T04:06:00+08:00",
    "assessments": [
      {
        "sector": "半导体/AI",
        "direction": "🔴 偏利空 (短期)",
        "significant": True,
        "hot_events": ["DeepSeek扩招", "Apple芯片转向", "AI芯片需求叙事松动"],
        "key_news": [
          "DeepSeek倍增扩招：低成本AI模型冲击NVDA芯片需求叙事",
          "Apple跳过M6 Pro/Max转向M7 AI核心，全线提价股价重挫6.12%",
          "NVDA 4月至今累涨23.5%，短线回调动能积蓄"
        ],
        "position_impact": "NVDA短线承压。DeepSeek叙事如果持续发酵，可能动摇AI芯片需求共识。但中长期AI资本开支趋势未变，回调可视为买入机会"
      },
      {
        "sector": "地缘/台海",
        "direction": "🟡 中性 (台海) / 🔴 偏利空 (中东)",
        "significant": True,
        "hot_events": ["霍尔木兹海峡冲突升级", "伊朗通行费方案", "台湾供应链分散"],
        "key_news": [
          "霍尔木兹海峡：伊朗要收通行费400亿/年，船只在阿曼湾遇袭",
          "各国加速半导体供应链去台湾化",
          "亚利桑那TSMC工厂被视为对华冲突时的生命线"
        ],
        "position_impact": "中东冲突升级利好原油、黄金、避险资产。霍尔木兹海峡是全球1/3石油运输通道，该地区风险溢价将维持高位"
      },
      {
        "sector": "美联储/货币政策",
        "direction": "🔴 利空 (美国加息风险)",
        "significant": True,
        "hot_events": ["Warsh加息预期", "BofA预测系列加息", "中美货币政策分化"],
        "key_news": [
          "Fed新主席Warsh面临首次重大考验：近半官员支持今年加息",
          "BofA：Fed今年将一系列加息打击通胀",
          "Fed Williams：通胀目标2%要到2028年实现",
          "中国央行明确降准降息、适度宽松货币政策"
        ],
        "position_impact": "美国加息预期压制成长股估值（NVDA/AAPL/MSFT等）。中国降准降息利好A/港股，但中美货币政策分化可能导致资金从中国流出。高利率+高VIX(21.67)组合不利于科技股"
      },
      {
        "sector": "贸易/访华",
        "direction": "🟡 中性偏积极",
        "significant": False,
        "hot_events": [],
        "key_news": [
          "Trump访华达成贸易协议，但细节不足，专家称对美国无实质收益",
          "农民期待实质性贸易协议落地"
        ],
        "position_impact": "中美关系短期缓和，但协议缺乏具体细节，市场已充分定价"
      },
      {
        "sector": "原材料 (钨/稀土)",
        "direction": "🔴 利空（对美股）/ 🟢利好（对中国出口方）",
        "significant": True,
        "hot_events": ["中国钨出口管制", "稀土定价权", "中东连锁反应"],
        "key_news": [
          "中国钨-日本2-4月出口降至零，价格飙升",
          "Washington Post：中国庆祝拥有美国需要的矿物",
          "中国收紧关键金属出口管制",
          "地缘联动：霍尔木兹海峡冲突->原油/黄金避险需求上升"
        ],
        "position_impact": "钨/稀土：出口管制利好中国上游企业（厦门钨业、中钨高新），利空美国军工和硬质合金下游。地缘乱局下黄金避险逻辑强化，原油供应链风险溢价上升"
      }
    ],
    "overall_narrative": "2026-06-25美股经历一轮科技股显著回调。核心驱动：(1) DeepSeek扩招引发的低成本AI模型冲击芯片需求叙事，NVDA一度跌3.5%；(2) Apple芯片战略大转向（跳过M6 Pro/Max）叠加全线涨价，股价暴跌6.12%；(3) Fed加息预期升温（BofA预测系列加息，Warsh面临考验）。VIX升至21.67，显示市场焦虑上升。中国方面：央行明确降准降息适度宽松，与Fed加息预期形成货币政策分化。地缘方面：霍尔木兹海峡冲突升级（伊朗收通行费+船只遇袭）是新的重要变量，将推高原油和黄金避险。",
    "buy_opportunities": [
      {
        "ticker": "NVDA",
        "logic": "短线受DeepSeek叙事冲击回调至195.74（-1.64%），但AI资本开支长期趋势未变。4月至今仍有+23.5%涨幅，回调至190以下可视为中期买入窗口。DeepSeek低成本AI叙事如果被证伪（实际训练需求仍大），反弹空间可观。",
        "risk": "Fed加息预期升温压制高估值成长股；如果Warsh 6月会议释放鹰派信号，NVDA可能继续回调至180区间"
      },
      {
        "asset": "黄金 (GLD/IAU)",
        "logic": "霍尔木兹海峡冲突+Fed加息不确定性+VIX>20三重避险驱动。中东地缘风险溢价上升，原油供应链扰动可能导致通胀预期回升，黄金作为实际利率对冲工具受益。",
        "risk": "如果中东局势快速缓解（伊朗收到通行费让步），避险情绪消退"
      },
      {
        "asset": "原油 (USO/XLE)",
        "logic": "霍尔木兹海峡占全球1/3石油运输，伊朗收取通行费计划+船只遇袭直接威胁供应安全。供给风险溢价将维持高位。",
        "risk": "美国释放SPR或OPEC增产可能压制涨幅；全球经济放缓削减需求"
      }
    ]
  }
}

output_path = '$HOME/stock_trader/market_events_latest.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Written: {output_path}")
# Verify
with open(output_path, 'r', encoding='utf-8') as f:
    v = json.load(f)
    print(f"OK: {len(v['sectors'])} sectors, {len(v['summary']['assessments'])} assessments, {len(v['summary']['buy_opportunities'])} opportunities")
