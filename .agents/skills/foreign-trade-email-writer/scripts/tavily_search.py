#!/usr/bin/env python3
"""
Tavily Search Tool - 网站调研工具
用于获取客户网站信息，生成精准开发信
"""

import os
import sys
import json

def search_website(url):
    """使用 Tavily API 搜索网站信息"""
    
    api_key = os.getenv('TAVILY_API_KEY')
    
    if not api_key:
        print("[Error] TAVILY_API_KEY not set")
        print("Please set environment variable: TAVILY_API_KEY")
        return None
    
    try:
        import requests
    except ImportError:
        print("[Error] requests library not installed")
        print("Run: pip install requests")
        return None
    
    # 构建搜索查询
    domain = url.replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
    
    search_queries = [
        f"{domain} company business products",
        f"{domain} what they do",
        f"site:{domain} about",
    ]
    
    results = {
        'domain': domain,
        'company_name': '',
        'business_type': '',
        'products': [],
        'industry': 'general',
        'pain_points': []
    }
    
    print(f"[Tavily] Searching information for: {domain}")
    
    for query in search_queries:
        try:
            response = requests.post(
                'https://api.tavily.com/search',
                headers={'Content-Type': 'application/json'},
                json={
                    'api_key': api_key,
                    'query': query,
                    'search_depth': 'comprehensive',
                    'include_answer': True,
                    'max_results': 5
                },
                timeout=30
            )
            
            data = response.json()
            
            if data.get('answer'):
                results['description'] = data['answer']
            
            for result in data.get('results', []):
                content = result.get('content', '').lower()
                title = result.get('title', '').lower()
                
                # 检测行业
                if any(kw in content or kw in title for kw in ['electronics', 'electronic', 'pcb', 'component']):
                    results['industry'] = 'electronics'
                    results['pain_points'] = ['component shortages', 'long lead times', 'quality control']
                elif any(kw in content or kw in title for kw in ['textile', 'fabric', 'clothing', 'apparel', 'fashion']):
                    results['industry'] = 'textile'
                    results['pain_points'] = ['quality inconsistency', 'long production cycles']
                elif any(kw in content or kw in title for kw in ['packaging', 'package', 'box', 'carton']):
                    results['industry'] = 'packaging'
                    results['pain_points'] = ['high costs', 'environmental concerns']
                elif any(kw in content or kw in title for kw in ['machinery', 'machine', 'equipment', 'industrial']):
                    results['industry'] = 'machinery'
                    results['pain_points'] = ['equipment downtime', 'parts availability']
                elif any(kw in content or kw in title for kw in ['consumer', 'retail', 'product', 'goods']):
                    results['industry'] = 'consumer'
                    results['pain_points'] = ['supplier reliability', 'delivery delays']
                
                # 提取产品关键词
                if 'product' in content:
                    # 简单提取产品信息
                    pass
            
            break  # 如果成功，不再尝试其他查询
            
        except Exception as e:
            print(f"[Warning] Search failed for query '{query}': {e}")
            continue
    
    # 设置默认值
    if not results['pain_points']:
        results['pain_points'] = ['supplier reliability', 'quality control', 'cost management']
    
    print(f"[Tavily] Found industry: {results['industry']}")
    print(f"[Tavily] Detected pain points: {', '.join(results['pain_points'])}")
    
    return results


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python tavily_search.py <website-url>")
        print("Example: python tavily_search.py https://example.com")
        sys.exit(1)
    
    url = sys.argv[1]
    result = search_website(url)
    
    if result:
        print("\n" + "="*50)
        print("SEARCH RESULTS")
        print("="*50)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("[Error] Failed to get website information")
        sys.exit(1)
