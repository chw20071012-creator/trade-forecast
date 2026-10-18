#!/bin/bash
VERSION="2.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS_PATH="$SCRIPT_DIR/settings.json"
QUEUE_PATH="$SCRIPT_DIR/send_queue.json"

INDUSTRY="general"
COMPANY=""
COUNTRY=""
PAINPOINT=""
VALUEPROP=""
SENDER=""
SENDER_COMPANY=""
MODE="auto"
URL=""
MAIL_ONLY=false

show_help() {
    cat << 'EOF'
B2B Cold Email Writer v2.0.0
Intelligence Hierarchy System - 3 Intelligence Levels

Commands:
  sequence     Generate 3-email sequence (with auto intelligence)
  first        Email 1: Connection
  second       Email 2: Value
  third        Email 3: Action
  subject      Generate subject lines
  followup     Follow-up email
  send         Send generated emails via SMTP
  queue        Show pending emails in send queue
  clear-queue  Clear send queue
  help         Show help

Intelligence Modes:
  --mode precise   Full personalization (requires: company, pain point)
  --mode auto      Auto-research from URL (requires: -u <url>)
  --mode blind     Generic outreach (requires: -mail-only or email only)

Options:
  -i, --industry <type>      Industry: textile|electronics|packaging|machinery|consumer|general
  -c, --company <name>       Target company name
  -co, --country <country>  Target country
  -p, --painpoint <issue>   Customer pain point
  -v, --valueprop <value>   Your value proposition
  -s, --sender <name>       Sender name
  -sc, --sender-company <co> Sender company
  -u, --url <url>           Target company URL (for auto mode)
  --mail-only               Run in blind mode

Examples:
  bash b2b-cold.sh sequence --mode precise -c "Tech Corp" -p "long lead times"
  bash b2b-cold.sh sequence --mode auto -u "www.targetclient.com"
  bash b2b-cold.sh sequence --mail-only
  bash b2b-cold.sh send
EOF
}

load_settings() {
    if [[ -f "$SETTINGS_PATH" ]]; then
        SETTINGS=$(cat "$SETTINGS_PATH")
    else
        SETTINGS=""
    fi
}

get_timezone_by_country() {
    local country="$1"
    case "${country^^}" in
        USA|US) echo "America/New_York" ;;
        UK|GB) echo "Europe/London" ;;
        DE) echo "Europe/Berlin" ;;
        FR) echo "Europe/Paris" ;;
        JP) echo "Asia/Tokyo" ;;
        CN) echo "Asia/Shanghai" ;;
        AU) echo "Australia/Sydney" ;;
        BR) echo "America/Sao_Paulo" ;;
        IN) echo "Asia/Kolkata" ;;
        *) echo "" ;;
    esac
}

get_optimal_send_time() {
    local country="$1"
    local tz=$(get_timezone_by_country "$country")

    if [[ -z "$tz" ]]; then
        date -d "+1 hour" "+%Y-%m-%d %H:%M:%S"
        return
    fi

    local offset=$(date -j -f "%Z" "$tz" "+%z" 2>/dev/null || echo "+0000")
    local target_hour=9
    local target_minute=30

    date -v+1d -j -f "%H%M" "${target_hour}${target_minute}" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || \
    date -d "+1 day +${target_hour}h ${target_minute}m" "+%Y-%m-%d %H:%M:%S"
}

invoke_auto_research() {
    local url="$1"
    echo "[Auto-Scanning] Researching $url ..."

    local business_type="retailer"
    local products=""
    local industry="general"
    local pain_points=""

    if command -v curl &> /dev/null; then
        content=$(curl -s -L -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" --max-time 15 "$url" 2>/dev/null | tr '[:upper:]' '[:lower:]')
    elif command -v wget &> /dev/null; then
        content=$(wget -q -O - -U "Mozilla/5.0" "$url" 2>/dev/null | tr '[:upper:]' '[:lower:]')
    else
        echo "[Warning] No HTTP client available, using generic defaults"
        echo "GENERIC:::general:::supplier reliability,quality control"
        return
    fi

    if echo "$content" | grep -qE "manufacturer|oem|factory|production"; then
        business_type="manufacturer"
    elif echo "$content" | grep -qE "distributor|wholesaler|supply"; then
        business_type="distributor"
    fi

    if echo "$content" | grep -qE "textile|fabric|garment|apparel|fashion"; then
        industry="textile"
    elif echo "$content" | grep -qE "electronic|component|pcb|semiconductor"; then
        industry="electronics"
    elif echo "$content" | grep -qE "packaging|carton|box|container"; then
        industry="packaging"
    elif echo "$content" | grep -qE "machinery|equipment|industrial|parts"; then
        industry="machinery"
    elif echo "$content" | grep -qE "consumer|retail|product|goods"; then
        industry="consumer"
    fi

    echo "${business_type}:::${industry}:::supplier reliability,quality control"
}

get_blind_hook() {
    local country="$1"
    local industry="$2"

    local hooks=(
        "I've been researching ${country}'s ${industry} market and noticed some interesting trends in supply chain optimization..."
        "Recent regulatory changes in ${country} are affecting how ${industry} companies approach their sourcing strategies..."
        "Many ${industry} companies in ${country} are facing challenges with cost control and supplier reliability..."
        "Based on our analysis, ${industry} businesses in ${country} are increasingly focusing on supply chain resilience..."
    )

    local random_index=$((RANDOM % ${#hooks[@]}))
    echo "${hooks[$random_index]}"
}

get_compliment() {
    local ind="$1"
    local company="$2"

    if [[ -n "$company" ]]; then
        echo "I've been following $company and love how you've been pushing the boundaries in the $ind space."
        return
    fi

    case "$ind" in
        textile) echo "I've been following brands in the fashion space and love how the industry is evolving." ;;
        electronics) echo "I've been impressed by innovation in the electronics space." ;;
        packaging) echo "I've been keeping an eye on brands that elevate product presentation." ;;
        machinery) echo "I've been following growth in the industrial sector." ;;
        consumer) echo "I've been following brands with innovative products." ;;
        *) echo "I've been following your company's growth and market presence." ;;
    esac
}

get_value() {
    local ind="$1"
    case "$ind" in
        textile) echo "premium fabrics, sustainable materials, custom prints" ;;
        electronics) echo "reliable components, competitive pricing, strict quality control" ;;
        packaging) echo "custom packaging, eco-friendly materials, unique designs" ;;
        machinery) echo "precision-engineered parts, OEM/ODM services, technical support" ;;
        consumer) echo "high-quality manufacturing, flexible MOQ, fast samples" ;;
        *) echo "high-quality products, competitive pricing, reliable delivery" ;;
    esac
}

get_painpoint() {
    local ind="$1"
    case "$ind" in
        textile) echo "quality inconsistency, long production cycles" ;;
        electronics) echo "component shortages, long lead times" ;;
        packaging) echo "high costs, environmental concerns" ;;
        machinery) echo "equipment downtime, parts availability" ;;
        consumer) echo "supplier reliability, delivery delays" ;;
        *) echo "supplier reliability, quality control" ;;
    esac
}

get_certificate() {
    local ind="$1"
    local certs=""

    if [[ -n "$SETTINGS" ]]; then
        certs=$(echo "$SETTINGS" | grep -o "\"${ind}\"".* | grep -o '"certifications":\[[^]]*\]' | sed 's/"certifications"://' | tr -d '[]"' | tr ',' ' ')
    fi

    if [[ -z "$certs" ]]; then
        echo "ISO 9001, CE"
    else
        echo "$certs"
    fi
}

generate_subjects() {
    echo ""
    echo "========================================"
    echo "HIGH-OPEN-RATE SUBJECT LINES"
    echo "========================================"
    echo ""
    echo "1. Quick question about your $INDUSTRY sourcing"
    if [[ -n "$PAINPOINT" ]]; then
        echo "2. Solving $PAINPOINT for $INDUSTRY companies"
    else
        echo "2. A better way to source $INDUSTRY products"
    fi
    if [[ -n "$COMPANY" ]]; then
        echo "3. $COMPANY + potential collaboration"
    else
        echo "3. Idea for your $INDUSTRY business"
    fi
    echo "4. Are you open to a quick chat about $INDUSTRY?"
    echo "5. Last try: $INDUSTRY opportunity"
    echo ""
}

generate_email_1() {
    local mode="$1"
    local hook="$2"
    local sender_name="${SENDER:-[Your Name]}"
    local sender_co="${SENDER_COMPANY:-[Your Company]}"

    echo "========================================"
    echo "EMAIL 1: BUILDING CONNECTION"
    echo "Mode: $mode - Low-pressure introduction"
    echo "========================================"
    echo ""
    echo "Subject: Quick question about your $INDUSTRY sourcing"
    echo ""
    echo "Hi there,"
    echo ""

    if [[ "$mode" == "blind" ]]; then
        local blind_hook=$(get_blind_hook "$COUNTRY" "$INDUSTRY")
        echo "$blind_hook"
        echo ""
        echo "I'm $sender_name from $sender_co. We specialize in $(get_value "$INDUSTRY") and have been helping companies like yours streamline their supply chain."
    elif [[ "$mode" == "auto" && -n "$hook" ]]; then
        echo "$hook"
        echo ""
        echo "I'm $sender_name from $sender_co. We specialize in $(get_value "$INDUSTRY")."
    else
        local compliment=$(get_compliment "$INDUSTRY" "$COMPANY")
        echo "$compliment"
        echo ""
        echo "I'm $sender_name from $sender_co. We specialize in $(get_value "$INDUSTRY")."
    fi

    echo ""
    echo "I'm not trying to sell you anything today—I just wanted to introduce myself and see if there's an opportunity for us to connect."

    if [[ -n "$COUNTRY" ]]; then
        echo "We've worked with several $COUNTRY companies already."
    else
        echo "We've helped many companies in the $INDUSTRY space."
    fi

    echo ""
    echo "If you have a few minutes next week, I'd be happy to chat about what trends or challenges you're seeing."
    echo ""
    echo "Any thoughts?"
    echo ""
    echo "Best regards,"
    echo "$sender_name"
    echo "$sender_co"
    echo ""
}

generate_email_2() {
    local mode="$1"
    local sender_name="${SENDER:-[Your Name]}"
    local sender_co="${SENDER_COMPANY:-[Your Company]}"
    local pp="${PAINPOINT:-$(get_painpoint "$INDUSTRY")}"
    local vp="${VALUEPROP:-$(get_value "$INDUSTRY")}"
    local co="${COMPANY:-your company}"
    local certs=$(get_certificate "$INDUSTRY")

    echo "========================================"
    echo "EMAIL 2: DELIVERING VALUE"
    echo "Mode: $mode - Address pain points"
    echo "========================================"
    echo ""
    echo "Subject: Re: Quick question about your $INDUSTRY sourcing"
    echo ""
    echo "Hi there,"
    echo ""
    echo "I wanted to follow up and share something that might interest you."
    echo ""
    echo "Many $INDUSTRY companies we work with were struggling with $pp before they found us."
    echo ""

    if [[ "$mode" == "precise" ]]; then
        echo "We've helped companies similar to $co achieve significant improvements by addressing exactly these challenges."
    fi

    echo "Here's what we bring to the table:"
    echo "• $vp"
    echo "• Dedicated account management"
    echo "• Flexible terms for growing businesses"
    echo "• $certs certified"
    echo ""
    echo "One of our clients saw a 30% improvement in their supply chain efficiency within 3 months of working with us."
    echo ""
    echo "Would you be open to a brief call to explore if we could help $co achieve similar results?"
    echo ""
    echo "Best regards,"
    echo "$sender_name"
    echo "$sender_co"
    echo ""
}

generate_email_3() {
    local mode="$1"
    local sender_name="${SENDER:-[Your Name]}"
    local sender_co="${SENDER_COMPANY:-[Your Company]}"
    local co="${COMPANY:-your company}"
    local vp="${VALUEPROP:-Better quality and faster delivery}"

    echo "========================================"
    echo "EMAIL 3: CALL TO ACTION"
    echo "Mode: $mode - Create urgency and get response"
    echo "========================================"
    echo ""
    echo "Subject: Last try: $INDUSTRY opportunity for $co"
    echo ""
    echo "Hi there,"
    echo ""
    echo "I don't want to clutter your inbox, so this will be my last email unless I hear back from you."
    echo ""
    echo "I truly believe we could help $co with:"
    echo "• $vp"
    echo "• Reducing supply chain headaches"
    echo "• Competitive pricing without compromising quality"
    echo ""

    if [[ "$mode" == "blind" ]]; then
        echo "If you're not actively looking for suppliers right now, I'd be happy to send you our free product catalog for future reference."
    else
        echo 'If now isn'\''t the right time, I completely understand. Just reply with "not now" and I'\''ll circle back in a few months.'
    fi

    echo ""
    echo "Otherwise, here's my calendar link: [Your Calendar Link]"
    echo "Or simply reply with a time that works for you."
    echo ""
    echo "Best regards,"
    echo "$sender_name"
    echo "$sender_co"
    echo "[Your Phone/WhatsApp]"
    echo ""
}

generate_followup() {
    local sender_name="${SENDER:-[Your Name]}"
    local sender_co="${SENDER_COMPANY:-[Your Company]}"
    local vp="${VALUEPROP:-how we could help with your $INDUSTRY sourcing}"

    echo "========================================"
    echo "FOLLOW-UP EMAIL (No Reply)"
    echo "========================================"
    echo ""
    echo "Subject: Bumping this up - $INDUSTRY sourcing"
    echo ""
    echo "Hi there,"
    echo ""
    echo "I know you're busy, so I'll keep this short."
    echo ""
    echo "I reached out about $vp and wanted to make sure my email didn't get lost in your inbox."
    echo ""
    echo "If this isn't a priority right now, no worries at all. Just let me know and I'll follow up at a better time."
    echo ""
    echo "If it is, I'd love to jump on a quick 10-minute call to see if we're a good fit."
    echo ""
    echo "What works best for you?"
    echo ""
    echo "Best regards,"
    echo "$sender_name"
    echo "$sender_co"
    echo ""
}

add_to_queue() {
    local to="$1"
    local subject="$2"
    local body="$3"
    local scheduled_time="$4"

    local entry=$(cat << EOF
{
  "id": "$(uuidgen 2>/dev/null || echo $RANDOM-$RANDOM-$RANDOM)",
  "to": "$to",
  "subject": "$subject",
  "body": "$body",
  "scheduled_time": "$scheduled_time",
  "status": "pending",
  "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
)

    if [[ -f "$QUEUE_PATH" ]]; then
        local existing=$(cat "$QUEUE_PATH")
        echo "[$existing, $entry]" > "$QUEUE_PATH"
    else
        echo "[$entry]" > "$QUEUE_PATH"
    fi

    echo "[Queue] Email to $to added. Scheduled: $scheduled_time"
}

show_queue() {
    if [[ -f "$QUEUE_PATH" ]]; then
        echo ""
        echo "Send Queue:"
        echo "========================================"
        cat "$QUEUE_PATH" | python3 -m json.tool 2>/dev/null || cat "$QUEUE_PATH"
    else
        echo "[Info] Queue is empty"
    fi
}

clear_queue() {
    if [[ -f "$QUEUE_PATH" ]]; then
        rm "$QUEUE_PATH"
        echo "[Info] Queue cleared"
    fi
}

resolve_intelligence_mode() {
    if [[ "$MAIL_ONLY" == true ]]; then
        echo "blind"
        return
    fi

    if [[ -n "$URL" ]]; then
        echo "auto"
        return
    fi

    if [[ -n "$COMPANY" && -n "$PAINPOINT" ]]; then
        echo "precise"
        return
    fi

    echo "auto"
}

get_auto_research_hook() {
    local research="$1"
    local business_type=$(echo "$research" | cut -d':' -f1)
    local products=$(echo "$research" | cut -d':' -f2)

    if [[ "$business_type" == "manufacturer" ]]; then
        echo "I've been researching companies that manufacture $products and noticed how supply chain optimization has become crucial for producers like yourselves..."
    elif [[ "$business_type" == "distributor" ]]; then
        echo "I've been studying the distribution landscape for $products and found that reliable supply partners make a significant difference..."
    else
        echo "I've been following companies like yours that are focused on delivering quality products to their customers..."
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -i|--industry) INDUSTRY="$2"; shift 2 ;;
            -c|--company) COMPANY="$2"; shift 2 ;;
            -co|--country) COUNTRY="$2"; shift 2 ;;
            -p|--painpoint) PAINPOINT="$2"; shift 2 ;;
            -v|--valueprop) VALUEPROP="$2"; shift 2 ;;
            -s|--sender) SENDER="$2"; shift 2 ;;
            -sc|--sender-company) SENDER_COMPANY="$2"; shift 2 ;;
            -u|--url) URL="$2"; shift 2 ;;
            --mode) MODE="$2"; shift 2 ;;
            --mail-only) MAIL_ONLY=true; shift ;;
            *) shift ;;
        esac
    done
}

load_settings
parse_args "$@"

RESOLVED_MODE=$(resolve_intelligence_mode)
AUTO_HOOK=""

if [[ "$RESOLVED_MODE" == "auto" && -n "$URL" ]]; then
    RESEARCH_RESULT=$(invoke_auto_research "$URL")
    INDUSTRY=$(echo "$RESEARCH_RESULT" | cut -d':' -f2)
    PAINPOINT=$(echo "$RESEARCH_RESULT" | cut -d':' -f3 | tr ',' '\n' | head -1)
    AUTO_HOOK=$(get_auto_research_hook "$RESEARCH_RESULT")
fi

case "${1:-help}" in
    sequence)
        generate_subjects
        generate_email_1 "$RESOLVED_MODE" "$AUTO_HOOK"
        generate_email_2 "$RESOLVED_MODE"
        generate_email_3 "$RESOLVED_MODE"
        ;;
    first)
        generate_email_1 "$RESOLVED_MODE" "$AUTO_HOOK"
        ;;
    second)
        generate_email_2 "$RESOLVED_MODE"
        ;;
    third)
        generate_email_3 "$RESOLVED_MODE"
        ;;
    subject)
        generate_subjects
        ;;
    followup)
        generate_followup
        ;;
    send)
        echo "[Info] Send functionality requires PowerShell on Windows. Use b2b-cold.ps1"
        ;;
    queue)
        show_queue
        ;;
    clear-queue)
        clear_queue
        ;;
    help|--help|-h|*)
        show_help
        ;;
esac