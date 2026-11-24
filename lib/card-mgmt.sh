#!/usr/bin/env bash
# lib/card-mgmt.sh — Fast Google Play Store card binding via ADB UI automation

_POSTAL_CODES_CLASSIC=("92101" "89101" "33131")
_POSTAL_CODES_TAXFREE=("97201" "97204" "19801" "03101")

_random_postal_code() {
    if [[ "${GTOOL_POSTAL_MODE:-classic}" == "taxfree" ]]; then
        local idx=$((RANDOM % ${#_POSTAL_CODES_TAXFREE[@]}))
        echo "${_POSTAL_CODES_TAXFREE[$idx]}"
    else
        local idx=$((RANDOM % ${#_POSTAL_CODES_CLASSIC[@]}))
        echo "${_POSTAL_CODES_CLASSIC[$idx]}"
    fi
}

_find_input_field() {
    local xml_file="${1:-}"
    local index="${2:-0}"
    [[ -z "$xml_file" || ! -s "$xml_file" ]] && return 1
    local match
    match=$($_GREP -oE '<node[^>]*class="android\.widget\.(EditText|AutoCompleteTextView)"[^>]*>' "$xml_file" | sed -n "$((index+1))p" || true)
    if [[ -n "$match" ]]; then
        $_GREP -m1 -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' <<< "$match" | sed 's/bounds="//;s/"//'
        return 0
    fi
    return 1
}

_xml_has_card_last4() {
    local xml_content="${1:-}"
    local last4="${2:-}"
    [[ -n "$last4" ]] && echo "$xml_content" | $_GREP -iqE "(mastercard|visa|amex|discover|jcb|••|\*\*\*\*|card)[^<\"]*-?${last4}"
}

bind_card_playstore() {
    local card_number="${1:-}"
    local card_expiry="${2:-}"
    local card_cvv="${3:-}"
    local card_postal="${4:-}"
    [[ -n "$card_number" && -n "$card_expiry" && -n "$card_cvv" ]] || { err "卡片参数不完整"; return 1; }
    local last4="${card_number: -4}"

    step_begin "绑定付款卡 ••••$last4"

    # Single page load: check if already bound AND tap Add Card from the SAME XML dump!
    adb_shell "am start -a android.intent.action.VIEW -p com.android.vending -d 'https://play.google.com/store/paymentmethods' || am start -a android.intent.action.VIEW -d 'https://play.google.com/store/paymentmethods'" >/dev/null
    sleep 1.2

    if ! wait_for_element 15 "Payment methods" "付款方式" "支付方式"; then
        warn "付款方式直链加载较慢，改从 Play 商店菜单进入..."
        adb_shell "am start -n com.android.vending/.AssetBrowserActivity" >/dev/null
        sleep 1.5
        _navigate_to_payment_methods || {
            press_back; press_back
            return 1
        }
        dump_ui >/dev/null
    fi

    local xml_file="$LAST_UI_FILE"
    local xml_content
    xml_content=$(<"$xml_file")

    # Already bound? Done immediately without a second page open!
    if _xml_has_card_last4 "$xml_content" "$last4"; then
        step_end "卡片 ••••$last4 已在账号中，无需重复绑定"
        go_home
        return 0
    fi

    # Tap "添加卡" / "Add card" directly from the cached XML ("添加卡" MUST precede "添加付款方式"!)
    if ! tap_in_xml "$xml_file" "添加卡" "Add card" "添加信用卡或借记卡" "Add credit or debit card" "Add payment method"; then
        sleep 0.6
        if ! tap_containing "添加卡" "Add card" "添加信用卡或借记卡" "Add credit or debit card" "Add payment method"; then
            err "未找到「添加卡」入口"
            take_screenshot "card_no_add_btn"
            press_back; press_back
            return 1
        fi
    fi
    sleep 1.2

    # Wait for either payment-type chooser OR card form directly
    local form_loaded=false
    local deadline=$((SECONDS + 14))
    while [[ $SECONDS -lt $deadline ]]; do
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")
        if $_GREP -iqE "卡号|Card number|所有字段" <<< "$xml_content"; then
            form_loaded=true
            break
        fi
        if $_GREP -iq "Credit or debit\|信用卡或借记卡" <<< "$xml_content"; then
            tap_in_xml "$xml_file" "Credit or debit" "信用卡或借记卡" || true
            sleep 1.0
            continue
        fi
        sleep 0.7
    done

    if ! $form_loaded; then
        err "添加银行卡表单未能加载"
        take_screenshot "card_form_no_load"
        press_back; press_back
        return 1
    fi

    # Pass already-dumped $xml_file directly into _fill_card_form (0ms initial dump!)
    _fill_card_form "$card_number" "$card_expiry" "$card_cvv" "$card_postal" "$xml_file" || {
        err "填写卡片表单失败"
        take_screenshot "card_form_fail"
        press_back; press_back; press_back
        return 1
    }

    sleep 0.3
    if ! tap_button "保存卡" "Save card" "Save" "保存" "Add" "确认"; then
        tap_containing "保存卡" "Save card" "Save" "保存" "Add" "确认" || press_enter
    fi
    sleep 2.0

    _handle_card_post_save "$card_postal" "$last4" || {
        take_screenshot "card_declined_or_fail"
        go_home
        return 1
    }

    # Verify card was added (first check current screen before re-opening URL!)
    xml_file=$(dump_ui)
    xml_content=$(<"$xml_file")
    if _xml_has_card_last4 "$xml_content" "$last4" || _check_card_bound "$last4"; then
        step_end "卡片 ••••$last4 绑定成功"
        go_home
        return 0
    fi

    err "未能确认卡片 ••••$last4 绑定结果"
    take_screenshot "card_verify_fail"
    go_home
    return 1
}

_navigate_to_payment_methods() {
    local xml_file bounds
    xml_file=$(dump_ui)
    if bounds=$(find_node_by_id "$xml_file" "avatar" 2>/dev/null); then
        tap_bounds "$bounds"
        sleep 1.2
    fi
    if tap_containing "Payments" "付款" "Payment" "支付" 2>/dev/null; then
        sleep 1.2
        tap_containing "Payment methods" "付款方式" 2>/dev/null
        sleep 1.2
        return 0
    fi
    return 1
}

_fill_card_form() {
    local card_number="${1:-}"
    local card_expiry="${2:-}"
    local card_cvv="${3:-}"
    local card_postal="${4:-}"
    local xml_file="${5:-}"

    [[ -z "$xml_file" || ! -s "$xml_file" ]] && xml_file=$(dump_ui)

    local num_bounds=""
    num_bounds=$(find_node_by_text "$xml_file" "卡号" "Card number") 2>/dev/null || \
        num_bounds=$(_find_input_field "$xml_file" 0) || {
            err "未找到卡号输入框"
            return 1
        }

    tap_bounds "$num_bounds"
    sleep 0.25
    type_text "$card_number"
    sleep 0.4

    # Re-dump once after card number reveals expiry + CVV fields
    xml_file=$(dump_ui)
    local exp_bounds=""
    exp_bounds=$(find_node_by_text "$xml_file" "失效日期" "MM/YY" "有效期" "Expiry") 2>/dev/null || \
        exp_bounds=$(_find_input_field "$xml_file" 1) 2>/dev/null || true
    if [[ -n "$exp_bounds" ]]; then
        tap_bounds "$exp_bounds"
        sleep 0.2
    else
        press_key "KEYCODE_TAB"
        sleep 0.2
    fi
    local exp_digits="${card_expiry//[^0-9]/}"
    type_text "${exp_digits:-$card_expiry}"
    sleep 0.35

    local cvv_bounds=""
    cvv_bounds=$(find_node_by_text "$xml_file" "CVV" "CVC" "安全码" "Security code") 2>/dev/null || \
        cvv_bounds=$(_find_input_field "$xml_file" 2) 2>/dev/null || true
    if [[ -n "$cvv_bounds" ]]; then
        tap_bounds "$cvv_bounds"
        sleep 0.2
    else
        press_key "KEYCODE_TAB"
        sleep 0.2
    fi
    type_text "$card_cvv"
    sleep 0.35

    adb_swipe_rel 50 65 50 30 320
    sleep 0.4

    xml_file=$(dump_ui)
    local zip_bounds=""
    zip_bounds=$(find_node_by_text "$xml_file" "账单邮寄地址" "邮政编码" "postal" "ZIP") 2>/dev/null || \
        zip_bounds=$(_find_input_field "$xml_file" 4) 2>/dev/null || true
    if [[ -n "$zip_bounds" ]]; then
        tap_bounds "$zip_bounds"
        sleep 0.25
        local zip_val="${card_postal:-$(_random_postal_code)}"
        type_text "$zip_val"
        sleep 0.4
    fi

    return 0
}

_handle_card_post_save() {
    local card_postal="${1:-}"
    local last4="${2:-}"
    local deadline=$((SECONDS + 18))
    while [[ $SECONDS -lt $deadline ]]; do
        local xml_file xml_content
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")

        if $_GREP -iqE "卡号无效|invalid card|declined|已被拒绝|更正此卡信息|无法添加" <<< "$xml_content"; then
            err "Google Play 拒绝了此卡或提示卡信息有误"
            return 1
        fi

        if _xml_has_card_last4 "$xml_content" "$last4" || $_GREP -iqE "卡已添加|Card added|已保存卡|Card saved" <<< "$xml_content"; then
            return 0
        fi

        if $_GREP -iq "address\|地址\|postal\|邮编\|ZIP" <<< "$xml_content"; then
            local zip_bounds
            zip_bounds=$(find_node_by_text "$xml_file" "ZIP" "Postal" "邮编" "邮政编码") 2>/dev/null || true
            if [[ -n "$zip_bounds" ]]; then
                tap_bounds "$zip_bounds"
                sleep 0.25
                type_text "${card_postal:-$(_random_postal_code)}"
                sleep 0.35
                tap_button_in_xml "$xml_file" "Save" "保存" "OK" "确定" "Done" "完成" "Continue" "继续" 2>/dev/null || \
                    tap_containing "Save" "保存" "OK" "确定" || press_enter
            else
                tap_in_xml "$xml_file" "Skip" "跳过" "Not now" "以后" "Cancel" "取消" 2>/dev/null || true
            fi
            sleep 0.8
            continue
        fi

        if $_GREP -iq "Verify\|验证\|Confirm\|确认" <<< "$xml_content"; then
            tap_in_xml "$xml_file" "OK" "确定" "Done" "完成" "Confirm" "确认" 2>/dev/null || true
            sleep 0.8
            continue
        fi

        sleep 1.0
    done
    return 0
}

_check_card_bound() {
    local last4="${1:-}"
    [[ -z "$last4" ]] && return 1
    adb_shell "am start -a android.intent.action.VIEW -p com.android.vending -d 'https://play.google.com/store/paymentmethods' || am start -a android.intent.action.VIEW -d 'https://play.google.com/store/paymentmethods'" >/dev/null
    sleep 1.5
    local xml_file xml_content
    xml_file=$(dump_ui)
    xml_content=$(<"$xml_file")
    if _xml_has_card_last4 "$xml_content" "$last4"; then
        press_back
        return 0
    fi
    press_back
    return 1
}

is_any_card_bound() {
    adb_shell "am start -a android.intent.action.VIEW -p com.android.vending -d 'https://play.google.com/store/paymentmethods' || am start -a android.intent.action.VIEW -d 'https://play.google.com/store/paymentmethods'" >/dev/null
    sleep 1.5
    local xml_file xml_content
    xml_file=$(dump_ui)
    xml_content=$(<"$xml_file")
    if $_GREP -iqE "visa|mastercard|amex|discover|••|信用卡|借记卡|\*\*\*\*" <<< "$xml_content"; then
        press_back
        return 0
    fi
    press_back
    return 1
}
