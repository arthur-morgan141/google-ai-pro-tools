#!/usr/bin/env bash
# lib/account-mgmt.sh — Fast Google account lifecycle on Android via ADB (cached XML & human gate)

_NEXT_TEXTS=("Next" "下一步" "NEXT" "下一个" "Siguiente" "다음" "次へ")
_AGREE_TEXTS=("I agree" "我同意" "Accept" "ACCEPT" "接受" "Agree" "同意" "Aceptar")
_SKIP_TEXTS=("Skip" "跳过" "Not now" "以后再说" "No thanks" "不用了" "Omitir")
_REMOVE_TEXTS=("Remove account" "移除帐号" "移除账号" "Remove" "删除账号" "Eliminar cuenta")
_MORE_TEXTS=("More options" "更多选项" "⋮")

_tap_dialog_confirm() {
    local xml_file bounds
    local deadline=$((SECONDS + 8))
    while [[ $SECONDS -lt $deadline ]]; do
        xml_file=$(dump_ui)
        bounds=$(find_node_by_id "$xml_file" "android:id/button1") 2>/dev/null && {
            tap_bounds "$bounds"
            return 0
        }
        bounds=$(tap_button_in_xml "$xml_file" "移除帐号" "移除账号" "Remove account" "Remove" "OK" "确定" "删除" && echo "tapped") || true
        [[ "$bounds" == "tapped" ]] && return 0
        for label in "移除帐号" "移除账号" "Remove account" "Remove" "OK" "确定" "删除"; do
            bounds=$(find_node_by_exact_text "$xml_file" "$label") 2>/dev/null && {
                tap_bounds "$bounds"
                return 0
            }
        done
        sleep 0.5
    done
    return 1
}

list_google_accounts() {
    adb_shell "dumpsys account" \
        | sed -n 's/.*Account *{name=\([^,]*\), *type=com\.google.*/\1/p' \
        | sort -u
}

is_account_on_device() {
    local email="${1:-}"
    [[ -n "$email" ]] && list_google_accounts | $_GREP -iqFx "$email"
}

# Switch Play Store active account cleanly
switch_play_account() {
    local email="${1:-}"
    [[ -z "$email" ]] && return 0
    local sq_email
    sq_email=$(_sh_sq "$email")
    adb_shell "am force-stop com.android.vending" >/dev/null 2>&1 || true
    adb_shell "am start -n com.android.vending/com.google.android.finsky.activities.MainActivity --es authAccount $sq_email" >/dev/null 2>&1 || \
        adb_shell "am start -n com.android.vending/.AssetBrowserActivity --es authAccount $sq_email" >/dev/null 2>&1 || true
    sleep 1.2
}

remove_google_account() {
    local email="${1:-}"
    [[ -z "$email" ]] && return 0
    log "正在移除旧账号: $email"

    if ! is_account_on_device "$email"; then
        log "账号已不在设备上"
        return 0
    fi

    adb_shell "am start --activity-clear-task -a android.settings.SYNC_SETTINGS" >/dev/null
    sleep 0.6

    if ! wait_for_element 10 "$email" "Google" "帐号" "账号" "Accounts"; then
        err "未能打开系统账号管理页"
        press_back; press_back
        return 1
    fi

    # Reuse $LAST_UI_FILE first (0ms cost!)
    if ! tap_in_xml "$LAST_UI_FILE" "$email"; then
        tap_in_xml "$LAST_UI_FILE" "Google" "google.com" && sleep 0.7
        if ! tap_containing "$email"; then
            err "界面中未找到账号 $email"
            press_back; press_back
            return 1
        fi
    fi
    sleep 0.6

    adb_swipe_rel 50 65 50 22 320
    sleep 0.3

    local xml_file
    xml_file=$(dump_ui)
    if ! tap_in_xml "$xml_file" "${_REMOVE_TEXTS[@]}"; then
        if tap_in_xml "$xml_file" "${_MORE_TEXTS[@]}"; then
            sleep 0.6
            tap_containing "${_REMOVE_TEXTS[@]}" || {
                err "未找到移除账号按钮"
                take_screenshot "remove_no_btn"
                press_back; press_back; press_back
                return 1
            }
        else
            err "未找到移除账号按钮"
            take_screenshot "remove_no_btn"
            press_back; press_back; press_back
            return 1
        fi
    fi
    sleep 0.5

    _tap_dialog_confirm || log "未检测到二次确认弹窗，校验结果..."
    sleep 0.6

    if is_account_on_device "$email"; then
        err "移除后账号仍存在: $email"
        press_back; press_back
        return 1
    fi

    ok "已移除账号: $email"
    go_home
    return 0
}

remove_all_accounts() {
    local accounts
    accounts=$(list_google_accounts)
    if [[ -z "$accounts" ]]; then
        log "当前设备无已登录 Google 账号"
        return 0
    fi

    local count=0
    while IFS= read -r email; do
        [[ -z "$email" ]] && continue
        remove_google_account "$email" && count=$((count + 1))
        sleep 0.5
    done <<< "$accounts"

    local remaining
    remaining=$(list_google_accounts)
    if [[ -n "$remaining" ]]; then
        err "仍有残留账号未能移除: $remaining"
        return 1
    fi

    ok "已清空 $count 个旧账号"
}

add_google_account() {
    local email="${1:-}"
    local password="${2:-}"
    local totp_secret="${3:-}"
    [[ -n "$email" && -n "$password" ]] || { err "缺少邮箱或密码参数"; return 1; }

    if is_account_on_device "$email"; then
        ok "目标账号已在设备上: $email"
        return 0
    fi

    step_begin "登录 Google 账号: $email"
    ensure_screen_on

    adb_shell "am start -a android.settings.ADD_ACCOUNT_SETTINGS --es account_types com.google" >/dev/null
    sleep 0.8

    local xml_file xml_content
    xml_file=$(dump_ui)
    xml_content=$(<"$xml_file")
    if ! $_GREP -q "com.google.android.gms" <<< "$xml_content"; then
        if tap_in_xml "$xml_file" "Google"; then
            sleep 2.0
        fi
    fi

    # Wait for email WebView input & reuse LAST_UI_FILE directly!
    if ! _wait_for_signin_page 25; then
        err "Google 登录页加载超时"
        return 1
    fi
    _tap_signin_input "$LAST_UI_FILE"
    sleep 0.25

    type_text "$email"
    sleep 0.35

    if ! tap_button "${_NEXT_TEXTS[@]}"; then
        tap_containing "${_NEXT_TEXTS[@]}" || press_enter
    fi
    log "邮箱已提交，等待密码页..."
    sleep 0.8

    # Wait for password page (also fail fast if account not found)
    if ! _wait_for_password_page 18; then
        xml_content=$(<"${LAST_UI_FILE:-/dev/null}" 2>/dev/null || echo "")
        if $_GREP -iqE "找不到此账号|找不到您的 Google|Couldn.t find your Google" <<< "$xml_content"; then
            err "Google 提示找不到此账号: $email"
            return 1
        fi
    fi

    _tap_signin_input "$LAST_UI_FILE"
    sleep 0.25

    type_secret "$password"
    sleep 0.35

    if ! tap_button "${_NEXT_TEXTS[@]}"; then
        tap_containing "${_NEXT_TEXTS[@]}" || press_enter
    fi
    log "密码已提交，处理验证与协议..."
    sleep 0.8

    if ! _handle_verification "$totp_secret"; then
        return 1
    fi

    local deadline=$((SECONDS + 75))
    local unknown_rounds=0
    while [[ $SECONDS -lt $deadline ]]; do
        if is_account_on_device "$email"; then
            step_end "账号登录完成: $email"
            go_home
            return 0
        fi

        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")

        # Fast-fail on wrong password
        if $_GREP -iqE "密码不正确|Wrong password" <<< "$xml_content"; then
            err "密码错误: $email"
            return 1
        fi

        # Human-in-the-loop gate if anti-bot / phone challenge appears (never auto-solve CAPTCHAs)
        if $_GREP -iqE "证明您不是自动程序|请输入电话号码|用于验证的电话号码|confirm you.re not a robot" <<< "$xml_content"; then
            if ! wait_human_assist "账号 $email 触发 Google 人机/手机验证"; then
                return 1
            fi
            deadline=$((SECONDS + 60))
            continue
        fi

        if _dismiss_setup_dialogs_in_xml "$xml_file"; then
            unknown_rounds=0
            sleep 0.8
            continue
        fi

        unknown_rounds=$((unknown_rounds + 1))
        sleep 1.0
    done

    err "等待账号写入系统超时: $email"
    go_home
    return 1
}

_tap_signin_input() {
    local xml_file="${1:-}"
    [[ -z "$xml_file" || ! -s "$xml_file" ]] && xml_file=$(dump_ui)
    local bounds
    bounds=$(find_node_by_id "$xml_file" "identifierId") 2>/dev/null && {
        tap_bounds "$bounds"
        return 0
    }
    bounds=$(find_edit_text "$xml_file" 0) 2>/dev/null && {
        tap_bounds "$bounds"
        return 0
    }
    adb_tap_rel 50 34
    return 0
}

_wait_for_signin_page() {
    local timeout="${1:-25}"
    local deadline=$((SECONDS + timeout))
    while [[ $SECONDS -lt $deadline ]]; do
        local xml_file xml_content
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")
        if $_GREP -qE 'class="android\.widget\.EditText"|identifier|identifierId|password' <<< "$xml_content"; then
            return 0
        fi
        sleep 0.5
    done
    return 1
}

_wait_for_password_page() {
    local timeout="${1:-18}"
    local deadline=$((SECONDS + timeout))
    while [[ $SECONDS -lt $deadline ]]; do
        local xml_file xml_content
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")
        if $_GREP -iqE 'password="true"|输入您的密码|Enter your password' <<< "$xml_content"; then
            return 0
        fi
        if $_GREP -iqE "找不到此账号|Couldn.t find your Google" <<< "$xml_content"; then
            return 1
        fi
        sleep 0.5
    done
    return 1
}

_handle_2fa_in_xml() {
    local xml_file="${1:-}"
    local totp_secret="${2:-}"

    log "检测到 2FA 两步验证，正在生成动态码..."
    local code
    code=$(generate_totp "$totp_secret")
    if [[ -z "$code" ]]; then
        err "TOTP 验证码生成失败"
        return 1
    fi

    tap_in_xml "$xml_file" "Authenticator" "身份验证器" 2>/dev/null && sleep 0.5 && xml_file=$(dump_ui)

    _tap_signin_input "$xml_file"
    sleep 0.25
    type_text "$code"
    sleep 0.35

    if ! tap_button "${_NEXT_TEXTS[@]}" "Verify" "验证" "Done" "完成"; then
        tap_containing "${_NEXT_TEXTS[@]}" "Verify" "验证" || press_enter
    fi
    log "已填入 2FA 验证码"
    sleep 0.8
    return 0
}

_handle_verification() {
    local totp_secret="${1:-}"
    sleep 0.6

    local xml_file xml_content attempt
    for attempt in 1 2 3 4 5; do
        xml_file=$(dump_ui)
        xml_content=$(<"$xml_file")

        if $_GREP -iqE "密码不正确|Wrong password" <<< "$xml_content"; then
            err "密码不正确"
            return 1
        fi

        if $_GREP -iqE "2.step verification|两步验证|enter.*code|输入验证码|authenticator" <<< "$xml_content"; then
            if [[ -n "$totp_secret" ]]; then
                _handle_2fa_in_xml "$xml_file" "$totp_secret" || return 1
            else
                wait_human_assist "该账号开启了两步验证但未配置 2FA 密钥，请手动输入验证码" || return 1
            fi
            sleep 0.8
            continue
        fi

        if $_GREP -iqE "验证身份|verify.*(it.s|your).*you|confirm.*identity|确认.*身份" <<< "$xml_content"; then
            log "检测到身份核验页..."
            if $_GREP -iqE "辅助邮箱|recovery.*email|确认您的辅助邮箱|confirm.*recovery|选择.*登录方式|choose.*sign.*in|try another way|试试其他方式" <<< "$xml_content"; then
                if [[ -n "${RECOVERY_EMAIL:-}" ]]; then
                    _handle_recovery_email "$xml_file" && { sleep 0.8; continue; }
                fi
            fi
            wait_human_assist "Google 请求身份核验，请在模拟器上协助完成" || return 1
            continue
        fi

        if $_GREP -iqE "服务条款|Terms of Service|我同意|I agree|隐私权政策|备份|backup|欢迎使用|Welcome to|Google 服务|Google services" <<< "$xml_content"; then
            return 0
        fi

        sleep 0.7
    done
    return 0
}

_handle_recovery_email() {
    local xml_file="${1:-}"
    log "尝试通过辅助邮箱完成核验..."

    if [[ -z "${RECOVERY_EMAIL:-}" ]]; then
        err "未提供辅助邮箱 RECOVERY_EMAIL"
        return 1
    fi

    [[ -z "$xml_file" || ! -s "$xml_file" ]] && xml_file=$(dump_ui)
    local found_input=false

    if ! tap_in_xml "$xml_file" "确认您的辅助邮箱" "Confirm your recovery email" 2>/dev/null; then
        log "WebView 选项树未暴露，采用坐标扫描点击辅助邮箱项..."
        local found=false ry
        for ry in 53 50 57 47 61; do
            adb_tap_rel 50 "$ry"
            sleep 1.1
            xml_file=$(dump_ui)
            if find_edit_text "$xml_file" 0 >/dev/null 2>&1; then
                found=true
                found_input=true
                break
            fi
            local page_text
            page_text=$(<"$xml_file")
            if ! $_GREP -q "选择您想要使用的登录方式" <<< "$page_text"; then
                if $_GREP -iq "输入验证码\|enter.*code" <<< "$page_text"; then
                    tap_in_xml "$xml_file" "试试其他方式" "Try another way" 2>/dev/null || adb_tap_rel 18 95
                    sleep 1.1
                    continue
                fi
                found=true
                break
            fi
        done
        if ! $found; then
            err "未能定位辅助邮箱选项"
            take_screenshot "recovery_select_fail"
            return 1
        fi
    else
        sleep 1.1
    fi

    if ! $found_input; then
        local deadline=$((SECONDS + 12))
        while [[ $SECONDS -lt $deadline ]]; do
            xml_file=$(dump_ui)
            if find_edit_text "$xml_file" 0 >/dev/null 2>&1; then
                found_input=true
                break
            fi
            sleep 0.6
        done
    fi

    if ! $found_input; then
        err "未出现辅助邮箱输入框"
        take_screenshot "recovery_input_fail"
        return 1
    fi

    _tap_signin_input "$xml_file"
    sleep 0.25
    type_text "$RECOVERY_EMAIL"
    sleep 0.35

    if ! tap_button "${_NEXT_TEXTS[@]}"; then
        tap_containing "${_NEXT_TEXTS[@]}" || press_enter
    fi
    log "已提交辅助邮箱"
    sleep 1.2
    return 0
}

# Zero-redundant-dump dialog dismisser (returns 0 if a dialog action was taken)
_dismiss_setup_dialogs_in_xml() {
    local xml_file="${1:-}"
    [[ -z "$xml_file" || ! -s "$xml_file" ]] && return 1
    local xml_content
    xml_content=$(<"$xml_file")

    if $_GREP -iq "I agree\|我同意\|Terms of Service\|服务条款" <<< "$xml_content"; then
        if tap_button_in_xml "$xml_file" "我同意" "I agree" "Accept" "同意" "接受"; then
            return 0
        fi
        tap_in_xml "$xml_file" "${_AGREE_TEXTS[@]}" 2>/dev/null && return 0
    fi

    if $_GREP -iq "提升使用体验\|improve your experience\|Google Play 下载" <<< "$xml_content"; then
        tap_button_in_xml "$xml_file" "关闭" "Close" "OK" 2>/dev/null && return 0
        tap_in_xml "$xml_file" "关闭" "Close" "OK" 2>/dev/null && return 0
    fi

    if $_GREP -iq "More\|更多\|scroll down" <<< "$xml_content"; then
        adb_swipe_rel 50 65 50 22 320
        sleep 0.5
        tap_button "${_AGREE_TEXTS[@]}" 2>/dev/null || true
        return 0
    fi

    if $_GREP -iq "备份\|backup\|back up" <<< "$xml_content"; then
        local toggle_match
        toggle_match=$($_GREP -m1 -oE '<node[^>]*class="android\.widget\.(Switch|ToggleButton)"[^>]*checked="true"[^>]*>' <<< "$xml_content" || true)
        if [[ -n "$toggle_match" ]]; then
            local bounds
            bounds=$($_GREP -m1 -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' <<< "$toggle_match" | sed 's/bounds="//;s/"//' || true)
            [[ -n "$bounds" ]] && tap_bounds "$bounds" && sleep 0.5
            xml_file=$(dump_ui)
        fi
        tap_in_xml "$xml_file" "不开启" "Don't turn on" "接受" "Accept" "${_SKIP_TEXTS[@]}" 2>/dev/null && return 0
    fi

    if $_GREP -iq "skip\|跳过\|not now\|以后再说\|No thanks\|不用了" <<< "$xml_content"; then
        tap_in_xml "$xml_file" "${_SKIP_TEXTS[@]}" 2>/dev/null && return 0
    fi

    if $_GREP -iq "Welcome\|欢迎\|Get started\|开始使用" <<< "$xml_content"; then
        tap_in_xml "$xml_file" "Accept" "接受" "OK" "确定" "Get started" "开始使用" 2>/dev/null && return 0
    fi

    if $_GREP -iq "手机号\|phone number\|辅助邮箱\|recovery email\|添加.*地址\|add.*address" <<< "$xml_content"; then
        tap_in_xml "$xml_file" "Cancel" "取消" "跳过" "Skip" "以后再说" "${_SKIP_TEXTS[@]}" 2>/dev/null && return 0
    fi

    if $_GREP -iq "Google.*服务\|Google.*services\|sync.*contacts\|同步.*通讯录" <<< "$xml_content"; then
        tap_in_xml "$xml_file" "接受" "Accept" "OK" "确定" "${_SKIP_TEXTS[@]}" 2>/dev/null && return 0
    fi

    return 1
}

_dismiss_setup_dialogs() {
    local xml_file
    xml_file=$(dump_ui) 2>/dev/null || return 0
    _dismiss_setup_dialogs_in_xml "$xml_file" || true
}
