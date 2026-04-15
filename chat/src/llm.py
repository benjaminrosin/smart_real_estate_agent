"""
LangChain integration with Google Gemini for conversational AI
"""
import json
import logging
import re
from typing import Any, Dict, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from . import config
from .listing_search import ListingSearchService

logger = logging.getLogger(__name__)

# System prompt for the real estate agent persona
SYSTEM_PROMPT = """You are a friendly and knowledgeable real estate agent assistant helping users find rental properties in Israel.

Primary language: Hebrew. Respond in Hebrew by default unless the user clearly asks for another language.

Your role:
- Help users understand what they're looking for in a rental property
- Ask clarifying questions about their preferences (location, budget, size, amenities)
- Provide helpful advice about the rental market
- Answer questions about neighborhoods, pricing, and rental processes
- Be conversational, friendly, and helpful
- If the user asks for listings, options, recommendations, or refinement (for example: "same area but cheaper"), proactively use the search tool.
- Never invent listings. Concrete recommendations must come from tool results.
- If essential constraints are missing, ask one short focused clarification question before searching.
- After each search, present exactly one recommended listing in full detail.
- After the recommended listing, suggest a few additional matching listings as short options.

CRITICAL FORMATTING RULES - MUST FOLLOW EXACTLY:
- ONLY use these Telegram-supported HTML tags:
  * <b>bold text</b> for emphasis
  * <i>italic text</i> for subtle emphasis
- ABSOLUTELY FORBIDDEN: 
  * DO NOT USE: **text** or *text* (markdown syntax)
    * DO NOT USE: <br>, <big>, <small>, <u>, <span>, <div>, <a>, <code>, <pre>
  * DO NOT USE: ANY HTML tags other than <b> and <i>
- Use simple line breaks (press Enter twice) to separate paragraphs
- For lists, use simple bullet points (•) or asterisks (*) with newlines between items
- Write naturally as if texting, with simple formatting
- Keep responses concise and natural - this is a chat interface

EXAMPLE OF CORRECT FORMATTING:
"I can help you find <b>apartments in Jerusalem</b>. What's your budget?

Popular areas include:
• Nachlaot
• City Center
• Katamon"

When users are ready to search, let them know you can help find specific listings.
"""

# Initialize the Gemini model
llm = ChatGoogleGenerativeAI(
    model=config.GEMINI_MODEL,
    temperature=0.7,
    max_retries=2,
    timeout=30,
)

listing_search = ListingSearchService(
    connection_string=config.MONGO_URI,
    database_name=config.DATABASE_NAME,
    collection_name=config.LISTINGS_COLLECTION,
    fetch_limit=config.SEARCH_FETCH_LIMIT,
    result_limit=config.SEARCH_RESULT_LIMIT,
)


def _sanitize_output(content: str) -> str:
    """Keep Telegram-compatible formatting only."""
    # Replace <br> with newline
    content = re.sub(r"<br\s*/?>", "\n", content)
    # Remove all HTML tags except <b>, </b>, <i>, </i>
    content = re.sub(r"<(?!/?(b|i)>)[^>]+>", "", content)
    # Convert markdown bold (**text**) to HTML <b>
    content = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", content)
    # Convert markdown italic (*text*) to HTML <i>
    content = re.sub(r"(?<!\*)\*(?!\*)([^*]+)\*(?!\*)", r"<i>\1</i>", content)
    return content


def _extract_text(response: Any) -> str:
    if hasattr(response, "content") and response.content is not None:
        if isinstance(response.content, list):
            parts = []
            for item in response.content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(str(item))
            return "\n".join(part for part in parts if part)
        return str(response.content)
    if hasattr(response, "text"):
        return str(response.text)
    return str(response)


def _truncate(value: Optional[str], length: int = 180) -> str:
    text = (value or "").replace("\n", " ").strip()
    if len(text) <= length:
        return text
    return text[:length] + "..."


@tool
def search_properties_from_context(
    user_request: str = "",
    city: Optional[str] = None,
    neighborhood: Optional[str] = None,
    property_type: Optional[str] = None,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    rooms_min: Optional[float] = None,
    rooms_max: Optional[float] = None,
    size_min: Optional[int] = None,
    size_max: Optional[int] = None,
    has_parking: Optional[bool] = None,
    has_elevator: Optional[bool] = None,
    has_mamad: Optional[bool] = None,
) -> str:
    """Search rental listings based on user preferences from the conversation context."""
    normalized_user_request = (user_request or "").strip()

    filters: Dict[str, Any] = {
        "city": city,
        "neighborhood": neighborhood,
        "property_type": property_type,
        "price_min": price_min,
        "price_max": price_max,
        "rooms_min": rooms_min,
        "rooms_max": rooms_max,
        "size_min": size_min,
        "size_max": size_max,
        "has_parking": has_parking,
        "has_elevator": has_elevator,
        "has_mamad": has_mamad,
        "user_request": normalized_user_request,
    }

    logger.info(
        "Tool call: search_properties_from_context city=%s neighborhood=%s price_min=%s price_max=%s rooms_min=%s rooms_max=%s",
        city,
        neighborhood,
        price_min,
        price_max,
        rooms_min,
        rooms_max,
    )
    logger.debug("Search tool request excerpt=%s", _truncate(normalized_user_request))

    result = listing_search.search(filters)
    formatted = listing_search.format_search_response(result)

    logger.info(
        "Tool result: candidates=%s top_returned=%s relaxed=%s",
        result.total_candidates,
        len(result.listings),
        result.relaxed_filters,
    )

    tool_payload = {
        "summary": formatted.get("assistant_text"),
        "primary_listing": formatted.get("primary_listing"),
        "listing_cards": formatted.get("listing_cards", []),
        "suggestions": formatted.get("suggestions", []),
        "used_filters": result.used_filters,
        "relaxed_filters": result.relaxed_filters,
        "total_candidates": result.total_candidates,
    }
    return json.dumps(tool_payload, ensure_ascii=False)


llm_with_tools = llm.bind_tools([search_properties_from_context])


def get_session_history(session_id: str) -> MongoDBChatMessageHistory:
    """
    Get or create chat history for a session (user).
    
    Args:
        session_id: Unique identifier for the chat session (typically chat_id)
        
    Returns:
        MongoDBChatMessageHistory instance for this session
    """
    return MongoDBChatMessageHistory(
        connection_string=config.MONGO_URI,
        database_name=config.DATABASE_NAME,
        collection_name=config.CHAT_HISTORY_COLLECTION,
        session_id=session_id,
    )


def chat(user_id: str, message: str) -> Dict[str, Any]:
    """
    Process a chat message with conversation history.
    
    Args:
        user_id: Unique user identifier (typically Telegram chat_id)
        message: The user's message
        
    Returns:
        Structured response payload with text and optional listing card
    """
    session_id = str(user_id)
    history = get_session_history(session_id)
    logger.info("Chat request received session_id=%s", session_id)
    logger.debug("User message excerpt=%s", _truncate(message))

    messages = [SystemMessage(content=SYSTEM_PROMPT), *history.messages, HumanMessage(content=message)]

    try:
        first_response = llm_with_tools.invoke(messages)
        tool_calls = getattr(first_response, "tool_calls", []) or []
        logger.debug("LLM first response tool_calls_count=%s", len(tool_calls))

        final_text: str
        structured_response: Optional[Dict[str, Any]] = None
        if tool_calls:
            messages.append(first_response)
            parsed_tool_payloads = []
            for call in tool_calls:
                if call.get("name") != search_properties_from_context.name:
                    continue
                logger.info("Executing tool call name=%s tool_call_id=%s", call.get("name"), call.get("id"))
                tool_args = dict(call.get("args", {}) or {})
                tool_args.setdefault("user_request", message)
                tool_output = search_properties_from_context.invoke(tool_args)
                try:
                    parsed = json.loads(tool_output)
                    if isinstance(parsed, dict):
                        parsed_tool_payloads.append(parsed)
                except Exception:
                    logger.debug("Failed to parse tool output JSON", exc_info=True)
                messages.append(
                    ToolMessage(content=tool_output, tool_call_id=call.get("id", "search_properties_tool"))
                )

            tool_payload = parsed_tool_payloads[-1] if parsed_tool_payloads else {}
            assistant_text = tool_payload.get("summary")
            primary_listing = tool_payload.get("primary_listing")
            listing_cards = tool_payload.get("listing_cards", [])
            if assistant_text:
                final_text = _sanitize_output(str(assistant_text))
                structured_response = {
                    "text": final_text,
                    "primary_listing": primary_listing,
                    "listing_cards": listing_cards,
                }
            else:
                final_response = llm.invoke(messages)
                final_text = _extract_text(final_response)
        else:
            final_text = _extract_text(first_response)
    except Exception:
        logger.exception("Chat processing failed session_id=%s", session_id)
        final_text = (
            "I had trouble running the property search just now. "
            "I can still help if you share city, budget, and rooms, and I will try again."
        )

    try:
        history.add_user_message(message)
    except Exception:
        logger.exception("Failed to persist user message session_id=%s", session_id)

    try:
        history.add_ai_message(final_text)
    except Exception:
        logger.exception("Failed to persist assistant message session_id=%s", session_id)

    logger.debug("History persistence attempted session_id=%s response_excerpt=%s", session_id, _truncate(final_text))

    if structured_response:
        return structured_response

    return {
        "text": _sanitize_output(final_text),
        "primary_listing": None,
        "listing_cards": [],
    }


def clear_history(user_id: str) -> None:
    """
    Clear conversation history for a user.
    
    Args:
        user_id: Unique user identifier
    """
    history = get_session_history(str(user_id))
    history.clear()
    logger.info("Chat history cleared session_id=%s", str(user_id))
