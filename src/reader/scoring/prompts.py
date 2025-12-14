"""Scoring prompt management.

REQ-RC-005: Track Scoring Prompt Changes Over Time
"""

DEFAULT_PROMPT = """You are helping curate a reading list for a software engineering manager with deep technical interests.

Interests (weighted by relevance):
- Systems programming, low-level performance, kernel work
- Weather/meteorology APIs and data processing
- Engineering management frameworks and practices
- Rust, distributed systems, infrastructure
- Deep technical explanations over surface-level news
- Long-form analysis over breaking news hot-takes

Dislikes:
- Product announcements unless they reveal interesting technical decisions
- Political hot-takes and inflammatory content
- Duplicate coverage of the same story
- Clickbait headlines
- Shallow "intro to X" content (senior-level reader)

Article to score:
Title: {title}
Source: {source}
Content preview: {content_preview}

Provide:
1. Relevance score (1-10, where 10 = definitely send to reading device)
2. Brief reasoning (1-2 sentences)
3. Estimated reading time category: 'quick' (<5min), 'medium' (5-15min), 'deep' (15+ min)
4. Suggested tags (max 3)

Respond in JSON:
{{
  "score": 8,
  "reasoning": "Brief explanation here",
  "reading_time": "medium",
  "tags": ["tag1", "tag2"]
}}"""

# TODO: Implement prompt version management
# - Store prompts in database
# - Track which prompt scored which articles
# - Support re-scoring with new prompts
