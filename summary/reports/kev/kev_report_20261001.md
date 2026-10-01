# KEV Report (2026-10-01)

- Window: last 31 days
- Inventory items: 0
- KEV rows in window: 45
- Report rows (after inventory filter): 45

## CVE-2026-76504
- Date added: 2026-09-30
- Vendor/Product: Cisco / Catalyst SD-WAN Manager
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-10-03
- Notes: https://sec.cloudapps.cisco.com/security/center/content/CiscoSecurityAdvisory/cisco-sa-sdwan-webauth-xr8beuuU ; ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-76504
- Matched local software: none
- Affected software and minimum safe version:
  - cisco:catalyst_sd-wan_manager | min_safe_version=20.9.10.1 | source=NVD
  - cisco:catalyst_sd-wan_manager | min_safe_version=20.12.8.2 | source=NVD
  - cisco:catalyst_sd-wan_manager | min_safe_version=20.15.6.1 | source=NVD
  - cisco:catalyst_sd-wan_manager | min_safe_version=20.18.4.1 | source=NVD
  - cisco:catalyst_sd-wan_manager | min_safe_version=26.1.2.1 | source=NVD
  - cisco:catalyst_sd-wan_manager | min_safe_version=unknown | source=NVD

## CVE-2026-86950
- Date added: 2026-09-29
- Vendor/Product: Apple / Multiple Products
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-10-02
- Notes: https://support.apple.com/en-us/149226 ; https://support.apple.com/en-us/149228 ; https://support.apple.com/en-us/149229 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-86950
- Matched local software: none
- Affected software and minimum safe version:
  - apple:ipados | min_safe_version=26.7.1 | source=NVD
  - apple:iphone_os | min_safe_version=26.7.1 | source=NVD
  - apple:macos | min_safe_version=15.8.1 | source=NVD
  - apple:macos | min_safe_version=26.7.1 | source=NVD

## CVE-2026-88772
- Date added: 2026-09-27
- Vendor/Product: Citrix / NetScaler
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-30
- Notes: Running the provided IOCs in the NetScaler console may help identify indicators of exploitation. Customers must conduct forensic triage as directed by BOD 26‑04 and follow Citrix’s published guidance for mitigations. For more information, please see: https://community.citrix.com/techzone-blogs/110_security-updates/netscaler-adc-and-netscaler-gateway-security-bulletin-for-cve-2026-88771-through-cve-2026-88778 ; https://support.citrix.com/support-home/kbsearch/article?articleNumber=CTX697096 ; https://support.citrix.com/external/article/CTX694799/steps-to-take-if-netscaler-adc-is-suspec.html ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-88772
- Matched local software: none
- Affected software and minimum safe version:
  - citrix:netscaler_application_delivery_controller | min_safe_version=13.1-64.23 | source=NVD
  - citrix:netscaler_application_delivery_controller | min_safe_version=13.1.37.279 | source=NVD
  - citrix:netscaler_application_delivery_controller | min_safe_version=14.1-73.37 | source=NVD
  - citrix:netscaler_application_delivery_controller | min_safe_version=>14.1-73.37 | source=NVD
  - citrix:netscaler_gateway | min_safe_version=13.1-64.23 | source=NVD
  - citrix:netscaler_gateway | min_safe_version=14.1-73.37 | source=NVD

## CVE-2026-88771
- Date added: 2026-09-27
- Vendor/Product: Citrix / NetScaler
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-30
- Notes: Running the provided IOCs in the NetScaler console may help identify indicators of exploitation. Customers must conduct forensic triage as directed by BOD 26‑04 and follow Citrix’s published guidance for mitigations. For more information, please see: https://community.citrix.com/techzone-blogs/110_security-updates/netscaler-adc-and-netscaler-gateway-security-bulletin-for-cve-2026-88771-through-cve-2026-88778 ; https://support.citrix.com/support-home/kbsearch/article?articleNumber=CTX697096 ; https://support.citrix.com/external/article/CTX694799/steps-to-take-if-netscaler-adc-is-suspec.html ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-88772
- Matched local software: none
- Affected software and minimum safe version:
  - citrix:netscaler_application_delivery_controller | min_safe_version=13.1-64.23 | source=NVD
  - citrix:netscaler_application_delivery_controller | min_safe_version=13.1.37.279 | source=NVD
  - citrix:netscaler_application_delivery_controller | min_safe_version=14.1-73.37 | source=NVD
  - citrix:netscaler_application_delivery_controller | min_safe_version=>14.1-73.37 | source=NVD
  - citrix:netscaler_gateway | min_safe_version=13.1-64.23 | source=NVD
  - citrix:netscaler_gateway | min_safe_version=14.1-73.37 | source=NVD

## CVE-2026-67279
- Date added: 2026-09-25
- Vendor/Product: MikroTik / RouterOS
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-28
- Notes: https://mikrotik.com/supportsec/september-2026-vulnerability/?utm_source=chatgpt.com ; ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-67279
- Matched local software: none
- Affected software and minimum safe version:
  - mikrotik:routeros | min_safe_version=6.49.21 | source=NVD
  - mikrotik:routeros | min_safe_version=7.23.4 | source=NVD
  - mikrotik:routeros | min_safe_version=7.24.2 | source=NVD

## CVE-2026-65660
- Date added: 2026-09-25
- Vendor/Product: Microsoft / SharePoint
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-28
- Notes: https://msrc.microsoft.com/update-guide/vulnerability/CVE-2026-65660 ; ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-65660
- Matched local software: none
- Affected software and minimum safe version:
  - microsoft:sharepoint_server | min_safe_version=16.0.19725.20522 | source=NVD
  - microsoft:sharepoint_server | min_safe_version=unknown | source=NVD

## CVE-2026-87902
- Date added: 2026-09-25
- Vendor/Product: WordPress / Core
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-28
- Notes: https://github.com/WordPress/wordpress-develop/security/advisories/GHSA-7hp8-65ch-5whp ; ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-87902
- Matched local software: none
- Affected software and minimum safe version:
  - wordpress:wordpress | min_safe_version=4.7.37 | source=NVD
  - wordpress:wordpress | min_safe_version=4.8.32 | source=NVD
  - wordpress:wordpress | min_safe_version=4.9.33 | source=NVD
  - wordpress:wordpress | min_safe_version=5.0.29 | source=NVD
  - wordpress:wordpress | min_safe_version=5.1.26 | source=NVD
  - wordpress:wordpress | min_safe_version=5.2.28 | source=NVD
  - wordpress:wordpress | min_safe_version=5.3.25 | source=NVD
  - wordpress:wordpress | min_safe_version=5.4.23 | source=NVD
  - wordpress:wordpress | min_safe_version=5.5.22 | source=NVD
  - wordpress:wordpress | min_safe_version=5.6.21 | source=NVD
  - wordpress:wordpress | min_safe_version=5.7.19 | source=NVD
  - wordpress:wordpress | min_safe_version=5.8.17 | source=NVD
  - wordpress:wordpress | min_safe_version=5.9.18 | source=NVD
  - wordpress:wordpress | min_safe_version=6.0.16 | source=NVD
  - wordpress:wordpress | min_safe_version=6.1.14 | source=NVD
  - wordpress:wordpress | min_safe_version=6.2.13 | source=NVD
  - wordpress:wordpress | min_safe_version=6.3.12 | source=NVD
  - wordpress:wordpress | min_safe_version=6.4.12 | source=NVD
  - wordpress:wordpress | min_safe_version=6.5.12 | source=NVD
  - wordpress:wordpress | min_safe_version=6.6.9 | source=NVD
  - wordpress:wordpress | min_safe_version=6.7.9 | source=NVD
  - wordpress:wordpress | min_safe_version=6.8.10 | source=NVD
  - wordpress:wordpress | min_safe_version=6.9.9 | source=NVD
  - wordpress:wordpress | min_safe_version=7.0.6 | source=NVD
  - wordpress:wordpress | min_safe_version=7.1.2 | source=NVD

## CVE-2026-5430
- Date added: 2026-09-24
- Vendor/Product: WSO2 / Multiple Products
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-27
- Notes: https://security.docs.wso2.com/en/latest/security-announcements/security-advisories/2026/WSO2-2026-5328/ ; ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-5430
- Matched local software: none
- Affected software and minimum safe version:
  - wso2:api_control_plane | min_safe_version=4.5.0.58 | source=NVD
  - wso2:api_control_plane | min_safe_version=4.6.0.22 | source=NVD
  - wso2:api_manager | min_safe_version=4.1.0.257 | source=NVD
  - wso2:api_manager | min_safe_version=4.2.0.197 | source=NVD
  - wso2:api_manager | min_safe_version=4.3.0.108 | source=NVD
  - wso2:api_manager | min_safe_version=4.4.0.72 | source=NVD
  - wso2:api_manager | min_safe_version=4.5.0.57 | source=NVD
  - wso2:api_manager | min_safe_version=4.6.0.21 | source=NVD
  - wso2:traffic_manager | min_safe_version=4.5.0.56 | source=NVD
  - wso2:traffic_manager | min_safe_version=4.6.0.21 | source=NVD
  - wso2:universal_gateway | min_safe_version=4.5.0.57 | source=NVD
  - wso2:universal_gateway | min_safe_version=4.6.0.21 | source=NVD

## CVE-2026-71362
- Date added: 2026-09-24
- Vendor/Product: Adobe / Commerce and Magento
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-27
- Notes: https://helpx.adobe.com/security/products/magento/apsb26-92.html ; ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-71362
- Matched local software: none
- Affected software and minimum safe version:
  - adobe:commerce | min_safe_version=2.4.4 | source=NVD
  - adobe:commerce | min_safe_version=unknown | source=NVD
  - adobe:commerce_b2b | min_safe_version=1.3.3 | source=NVD
  - adobe:commerce_b2b | min_safe_version=unknown | source=NVD
  - adobe:magento | min_safe_version=>2.4.6 | source=NVD
  - adobe:magento | min_safe_version=unknown | source=NVD

## CVE-2026-93952
- Date added: 2026-09-22
- Vendor/Product: Arista / VeloCloud Orchestrator
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-25
- Notes: https://www.arista.com/en/support/advisories-notices/security-advisory/24765-security-advisory-0183 ; ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-93952
- Matched local software: none
- Affected software and minimum safe version:
  - arista:velocloud_orchestrator | min_safe_version=5.2.3.16 | source=NVD
  - arista:velocloud_orchestrator | min_safe_version=>6.1.3.7 | source=NVD
  - arista:velocloud_orchestrator | min_safe_version=6.4.2.8 | source=NVD
  - arista:velocloud_orchestrator | min_safe_version=>7.0.0.2 | source=NVD

## CVE-2026-94127
- Date added: 2026-09-22
- Vendor/Product: F5 / BIG-IP APM
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-25
- Notes: For temporary mitigation to allow for proactive forensic triage, apply the vendor-provided iRule. Once completed, install the final vendor patch as soon as possible. For more information please see: https://my.f5.com/manage/s/article/K000162605 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-94127
- Matched local software: none
- Affected software and minimum safe version:
  - f5:big-ip_access_policy_manager | min_safe_version=>17.1.3 | source=NVD
  - f5:big-ip_access_policy_manager | min_safe_version=>17.5.1 | source=NVD
  - f5:big-ip_access_policy_manager | min_safe_version=unknown | source=NVD

## CVE-2026-93616
- Date added: 2026-09-22
- Vendor/Product: Check Point / Multiple Products
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-25
- Notes: https://support.checkpoint.com/results/sk/sk1000171/ ; ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-93616
- Matched local software: none
- Affected software and minimum safe version:
  - checkpoint:multi-domain_security_management | min_safe_version=r81.10 | source=NVD
  - checkpoint:multi-domain_security_management | min_safe_version=unknown | source=NVD
  - checkpoint:quantum_security_management | min_safe_version=r81.10 | source=NVD
  - checkpoint:quantum_security_management | min_safe_version=unknown | source=NVD

## CVE-2026-85102
- Date added: 2026-09-22
- Vendor/Product: Check Point / Multiple Products
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-25
- Notes: https://support.checkpoint.com/results/sk/sk1000117 ; ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-85102
- Matched local software: none
- Affected software and minimum safe version:
  - checkpoint:gaia_embedded | min_safe_version=r81.10.17 | source=NVD
  - checkpoint:gaia_embedded | min_safe_version=r82.00.10 | source=NVD
  - checkpoint:gaia_embedded | min_safe_version=unknown | source=NVD
  - checkpoint:gaia_os | min_safe_version=r81.10 | source=NVD
  - checkpoint:gaia_os | min_safe_version=unknown | source=NVD

## CVE-2026-7273
- Date added: 2026-09-21
- Vendor/Product: Zyxel / GS1900 Series Switches
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-24
- Notes: https://www.zyxel.com/global/en/support/security-advisories/zyxel-security-advisory-for-stack-based-buffer-overflow-vulnerability-in-gs1900-series-switches-06-16-2026 ; ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-7273
- Matched local software: none
- Affected software and minimum safe version:
  - zyxel:gs1900-8_firmware | min_safe_version=2.90\(aahh.2\)c0 | source=NVD
  - zyxel:gs1900-8hp_firmware | min_safe_version=2.90\(aahi.2\)c0 | source=NVD
  - zyxel:gs1900-10hp_firmware | min_safe_version=2.90\(aazi.2\)c0 | source=NVD
  - zyxel:gs1900-16_firmware | min_safe_version=2.90\(aahj.2\)c0 | source=NVD
  - zyxel:gs1900-24_firmware | min_safe_version=2.90\(aahl.2\)c0 | source=NVD
  - zyxel:gs1900-24e_firmware | min_safe_version=2.90\(aahk.2\)c0 | source=NVD
  - zyxel:gs1900-24ep_firmware | min_safe_version=2.90\(abto.2\)c0 | source=NVD
  - zyxel:gs1900-24hpv2_firmware | min_safe_version=2.90\(abtp.2\)c0 | source=NVD
  - zyxel:gs1900-48_firmware | min_safe_version=2.90\(aahn.2\)c0 | source=NVD
  - zyxel:gs1900-48hpv2_firmware | min_safe_version=2.90\(abtq.2\)c0 | source=NVD

## CVE-2025-39964
- Date added: 2026-09-18
- Vendor/Product: Linux / Kernel
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-21
- Notes: This vulnerability affects an open-source component, third-party library, protocol, or proprietary implementation that could be used by different products. For more information, please see: ; https://git.kernel.org/stable/c/0f28c4adbc4a97437874c9b669fd7958a8c6d6ce; https://git.kernel.org/stable/c/e4c1ec11132ec466f7362a95f36a506ce4dc08c9; https://git.kernel.org/stable/c/1f323a48e9b5ebfe6dc7d130fdf5c3c0e92a07c8; https://git.kernel.org/stable/c/7c4491b5644e3a3708f3dbd7591be0a570135b84; https://git.kernel.org/stable/c/9aee87da5572b3a14075f501752e209801160d3d; https://git.kernel.org/stable/c/45bcf60fe49b37daab1acee57b27211ad1574042; https://git.kernel.org/stable/c/1b34cbbf4f011a121ef7b2d7d6e6920a036d5285 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2025-39964
- Matched local software: none
- Affected software and minimum safe version:
  - Linux:Kernel | min_safe_version=6.16.9 | source=OSV

## CVE-2026-53266
- Date added: 2026-09-18
- Vendor/Product: Linux / Kernel
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-21
- Notes: This vulnerability affects an open-source component, third-party library, protocol, or proprietary implementation that could be used by different products. For more information, please see: ; https://git.kernel.org/stable/c/bf84ad7c7a9ede46e31afaa41a1ba06a159e8c87; https://git.kernel.org/stable/c/76280b78cc9f23bdc6438e10ad6dff148ef8375b; https://git.kernel.org/stable/c/b7e91939ba9be805a62a257fa4e227dffbb88fa0; https://git.kernel.org/stable/c/afd64b59c3de9bbbdd3759e834fdc55cda716e0b; https://git.kernel.org/stable/c/153ea96c806aea395daba907a4f88480b6ad5093; https://git.kernel.org/stable/c/b18675263db1147c8e1cab625400c13a0d87bd2d; https://git.kernel.org/stable/c/c9b5ff59feffb92a147a84a5aa28acd2cb8ff4c5; https://git.kernel.org/stable/c/67ba971ae02514d85818fe0c32549ab4bfa3bf49 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-53266
- Matched local software: none
- Affected software and minimum safe version:
  - Linux:Kernel | min_safe_version=7.0.13 | source=OSV

## CVE-2025-39682
- Date added: 2026-09-18
- Vendor/Product: Linux / Kernel
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-21
- Notes: This vulnerability affects an open-source component, third-party library, protocol, or proprietary implementation that could be used by different products. For more information, please see: ; https://git.kernel.org/stable/c/2902c3ebcca52ca845c03182000e8d71d3a5196f; https://git.kernel.org/stable/c/c09dd3773b5950e9cfb6c9b9a5f6e36d06c62677; https://git.kernel.org/stable/c/3439c15ae91a517cf3c650ea15a8987699416ad9; https://git.kernel.org/stable/c/29c0ce3c8cdb6dc5d61139c937f34cb888a6f42e; https://git.kernel.org/stable/c/62708b9452f8eb77513115b17c4f8d1a22ebf843 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2025-39682
- Matched local software: none
- Affected software and minimum safe version:
  - Linux:Kernel | min_safe_version=6.16.4 | source=OSV

## CVE-2026-58704
- Date added: 2026-09-16
- Vendor/Product: Google / Pixel
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-19
- Notes: https://source.android.com/docs/security/bulletin/pixel/2026/2026-09-01 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-58704
- Matched local software: none
- Affected software and minimum safe version:
  - google:android | min_safe_version=unknown | source=NVD

## CVE-2026-76460
- Date added: 2026-09-16
- Vendor/Product: Cisco / Identity Services Engine
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-19
- Notes: https://sec.cloudapps.cisco.com/security/center/content/CiscoSecurityAdvisory/cisco-sa-ISE-ABP-VNSW7Tn5 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-76460
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-87886
- Date added: 2026-09-16
- Vendor/Product: Acronis / Backup
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-19
- Notes: https://security-advisory.acronis.com/advisories/SEC-10986 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-87886
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-76461
- Date added: 2026-09-14
- Vendor/Product: Cisco / Secure Email Gateway
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-17
- Notes: https://sec.cloudapps.cisco.com/security/center/content/CiscoSecurityAdvisory/cisco-sa-esa-inj-2bLVGmhX ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-76461
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-84869
- Date added: 2026-09-11
- Vendor/Product: ConnectWise / ScreenConnect
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-14
- Notes: https://www.connectwise.com/company/trust/security-bulletins/2026-09-08-screenconnect-bulletin ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-84869
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-42016
- Date added: 2026-09-11
- Vendor/Product: JFrog / Artifactory
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-25
- Notes: https://docs.jfrog.com/releases/docs/jfrog-security-advisories ; https://docs.jfrog.com/releases/docs/artifactory-self-managed-releases ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-42016
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-42018
- Date added: 2026-09-11
- Vendor/Product: JFrog / Artifactory
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-25
- Notes: https://docs.jfrog.com/releases/docs/jfrog-security-advisories ; https://docs.jfrog.com/releases/docs/artifactory-self-managed-releases ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-42018
- Matched local software: none
- Affected software and minimum safe version:
  - jfrog:artifactory | min_safe_version=7.111.20 | source=NVD
  - jfrog:artifactory | min_safe_version=7.117.27 | source=NVD
  - jfrog:artifactory | min_safe_version=7.125.19 | source=NVD
  - jfrog:artifactory | min_safe_version=7.133.28 | source=NVD
  - jfrog:artifactory | min_safe_version=7.146.8 | source=NVD

## CVE-2026-85706
- Date added: 2026-09-11
- Vendor/Product: GitLab / Community Edition and Enterprise Edition
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-14
- Notes: https://docs.gitlab.com/releases/patches/patch-release-gitlab-19-3-2-released/ ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-85706
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-86060
- Date added: 2026-09-10
- Vendor/Product: MikroTik / RouterOS
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-13
- Notes: https://mikrotik.com/supportsec/september-2026-vulnerability ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-86060
- Matched local software: none
- Affected software and minimum safe version:
  - mikrotik:routeros | min_safe_version=6.49.21 | source=NVD
  - mikrotik:routeros | min_safe_version=7.23.4 | source=NVD
  - mikrotik:routeros | min_safe_version=7.24.2 | source=NVD

## CVE-2026-67277
- Date added: 2026-09-10
- Vendor/Product: MikroTik / RouterOS
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-13
- Notes: https://mikrotik.com/supportsec/september-2026-vulnerability/ ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-67277
- Matched local software: none
- Affected software and minimum safe version:
  - mikrotik:routeros | min_safe_version=6.49.21 | source=NVD
  - mikrotik:routeros | min_safe_version=7.23.4 | source=NVD
  - mikrotik:routeros | min_safe_version=7.24.2 | source=NVD

## CVE-2026-19490
- Date added: 2026-09-09
- Vendor/Product: Citrix / NetScaler
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-12
- Notes: https://support.citrix.com/external/article/CTX696939/netscaler-adc-and-netscaler-gateway-secu.html ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-19490
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2025-25249
- Date added: 2026-09-09
- Vendor/Product: Fortinet / Multiple Products
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-12
- Notes: https://fortiguard.fortinet.com/psirt/FG-IR-25-084 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2025-25249
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-87491
- Date added: 2026-09-09
- Vendor/Product: Google / Chromium V8
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-23
- Notes: https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_0808145027.html ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-87491
- Matched local software: none
- Affected software and minimum safe version:
  - google:chrome | min_safe_version=153.0.8010.36 | source=NVD

## CVE-2026-20079
- Date added: 2026-09-09
- Vendor/Product: Cisco / Secure Firewall Management Center (FMC) and Security Cloud Control (SCC) Firewall Management
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-12
- Notes: https://sec.cloudapps.cisco.com/security/center/content/CiscoSecurityAdvisory/cisco-sa-onprem-fmc-authbypass-5JPp45V2 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-20079
- Matched local software: none
- Affected software and minimum safe version:
  - cisco:secure_firewall_management_center | min_safe_version=unknown | source=NVD

## CVE-2026-75650
- Date added: 2026-09-08
- Vendor/Product: Adobe / Commerce and Magento
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-11
- Notes: https://helpx.adobe.com/security/products/magento/apsb26-146.html ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-75650
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-81963
- Date added: 2026-09-08
- Vendor/Product: Microsoft / Windows
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-22
- Notes: https://msrc.microsoft.com/update-guide/en-US/vulnerability/CVE-2026-81963 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-81963
- Matched local software: none
- Affected software and minimum safe version:
  - microsoft:windows_11_23h2 | min_safe_version=10.0.22631.7582 | source=NVD
  - microsoft:windows_11_24h2 | min_safe_version=10.0.26100.9445 | source=NVD
  - microsoft:windows_11_25h2 | min_safe_version=10.0.26200.9445 | source=NVD
  - microsoft:windows_11_26h1 | min_safe_version=10.0.28000.2954 | source=NVD
  - microsoft:windows_server_2025 | min_safe_version=10.0.26100.33438 | source=NVD

## CVE-2026-86218
- Date added: 2026-09-08
- Vendor/Product: N-able / N-central
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-11
- Notes: https://status.n-able.com/2026/09/06/n-central-2026-3-hotfix-4-cve-2026-86218/ ; https://me.n-able.com/s/security-advisory/aArVy0000002Ld3KAE/cve202686218-preauthentication-remote-code-execution ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-86218
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-85880
- Date added: 2026-09-08
- Vendor/Product: Microsoft / Windows
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-22
- Notes: https://msrc.microsoft.com/update-guide/en-US/vulnerability/CVE-2026-85880 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-85880
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-85046
- Date added: 2026-09-04
- Vendor/Product: Google / Chromium V8
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-18
- Notes: https://chromereleases.googleblog.com/2026/09/stable-channel-update-for-desktop_01882797386.html ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-85046
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-59822
- Date added: 2026-09-02
- Vendor/Product: BerriAI / LiteLLM
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-16
- Notes: https://github.com/BerriAI/litellm/security/advisories/GHSA-7488-6r32-c95q ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-59822
- Matched local software: none
- Affected software and minimum safe version:
  - litellm:litellm | min_safe_version=1.84.0 | source=NVD

## CVE-2026-48710
- Date added: 2026-09-02
- Vendor/Product: Kludex / Starlette
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-16
- Notes: This vulnerability affects an open-source component, third-party library, protocol, or proprietary implementation that could be used by different products. For more information, please see: https://github.com/Kludex/starlette/security/advisories/GHSA-86qp-5c8j-p5mr ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-48710
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-49869
- Date added: 2026-09-02
- Vendor/Product: Kestra / Kestra OSS
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-05
- Notes: This vulnerability affects an open-source component, third-party library, protocol, or proprietary implementation that could be used by different products. For more information, please see: https://github.com/kestra-io/kestra/security/advisories/GHSA-5vc5-wxxq-3fjx ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-49869
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-82329
- Date added: 2026-09-02
- Vendor/Product: JFrog / Artifactory
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-05
- Notes: https://docs.jfrog.com/releases/docs/jfrog-security-advisories ; https://docs.jfrog.com/releases/docs/artifactory-self-managed-releases ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-82329
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-9586
- Date added: 2026-09-02
- Vendor/Product: Sangoma / Switchvox
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-05
- Notes: https://sangomakb.atlassian.net/wiki/spaces/Switchvox/pages/1802371073/Switchvox+-+Release+Notes+Version+8.4.0.2+July+14+2026 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-9586
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-83548
- Date added: 2026-09-02
- Vendor/Product: SonicWall / SMA1000 Appliances
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-05
- Notes: https://psirt.global.sonicwall.com/vuln-detail/SNWLID-2026-0016 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-83548
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-83549
- Date added: 2026-09-02
- Vendor/Product: SonicWall / SMA1000 Appliances
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-05
- Notes: https://psirt.global.sonicwall.com/vuln-detail/SNWLID-2026-0016 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-83549
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-82078
- Date added: 2026-08-31
- Vendor/Product: PaperCut / NG/MF
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-14
- Notes: https://www.papercut.com/kb/Main/security-bulletin-27-aug-2026-urgent-security-advisory/?lid=2oneu2wt0ct4 ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-82078
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)

## CVE-2026-81578
- Date added: 2026-08-31
- Vendor/Product: PaperCut / NG/MF
- Required action: Apply mitigations in accordance with vendor instructions, ensuring compliance with CISA’s BOD 26-04 Prioritizing Security Updates Based on Risk (see URL in Notes) guidance and CISA’s “Forensics Triage Requirements” (see URL in Notes). Follow applicable BOD 26-04 guidance for cloud services or discontinue use of the product if mitigations are unavailable. Stakeholders are responsible for evaluating each asset's internet exposure and ensuring adherence to BOD 26-04 patching guidelines.
- KEV due date: 2026-09-14
- Notes: https://www.papercut.com/kb/Main/security-bulletin-27-aug-2026-urgent-security-advisory/ ; BOD 26-04: https://www.cisa.gov/news-events/directives/bod-26-04-prioritizing-security-updates-based-risk ; Forensics Triage Requirements: https://www.cisa.gov/news-events/directives/bod-26-04-implementation-guidance-prioritizing-security-updates-based-risk ; https://nvd.nist.gov/vuln/detail/CVE-2026-81578
- Matched local software: none
- Affected software and minimum safe version:
  - unknown (no OSV/NVD mapping found)
