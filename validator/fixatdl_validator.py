#!/usr/bin/env python3
"""
fixatdl_validator.py  --  Standalone programmatic validator for FIXatdl 1.1.

This is a single, self-contained module (Python standard library only) that
encodes the rules of the *FIX Algorithmic Trading Definition Language*
(FIXatdl) version 1.1 Specification with Errata 20101221.

The rules are derived from the specification text and the six XML Schema files
that accompany it:

    fixatdl-core-1-1.xsd        fixatdl-validation-1-1.xsd
    fixatdl-layout-1-1.xsd      fixatdl-flow-1-1.xsd
    fixatdl-regions-1-1.xsd     fixatdl-timezones-1-1.xsd

Every rule is given a stable rule ID (see RULES below).  Validation returns a
JSON-serialisable dict:

    {
        "valid":   <bool>,            # True iff there are zero error-level findings
        "source":  <str>,             # file path or "<string>"
        "summary": {"errors": N, "warnings": M, "rules": <count>},
        "errors":  [ {rule_id, severity, message, element, attribute, line}, ... ]
    }

Findings of severity "warning" do NOT make a document invalid; only "error"
findings do.

Usage (CLI):

    python fixatdl_validator.py path/to/document.xml [--pretty] [--warnings-as-errors]

Usage (library):

    from fixatdl_validator import validate_file, validate_string
    result = validate_file("document.xml")
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from xml.parsers import expat


# ---------------------------------------------------------------------------
# Rule catalogue
# ---------------------------------------------------------------------------
# Human-readable description of every rule the validator enforces.  The keys are
# the rule IDs emitted in findings.  Categories:
#   DOC-*    document / root <Strategies> element
#   STR-*    <Strategy> element
#   PARAM-*  <Parameter> element and its typed attributes
#   ENUM-*   <EnumPair> element
#   EDIT-*   <Edit> boolean expressions (validation & flow control)
#   EREF-*   <EditRef> element
#   SEDIT-*  <StrategyEdit> validation rule
#   SRULE-*  <StateRule> flow-control rule
#   CTRL-*   <Control> element and its typed attributes
#   LAY-*    <StrategyLayout> / <StrategyPanel> layout containers
#   GEO-*    <Regions>/<Markets>/<SecurityTypes> scoping elements
#   RG-*     <RepeatingGroup> element
#   XML-*    well-formedness
RULES = {
    "XML-01": "Document must be well-formed XML.",
    # ---- document / root ----
    "DOC-01": "Root element must be <Strategies>.",
    "DOC-02": "Strategies/@strategyIdentifierTag is required.",
    "DOC-03": "Strategies/@strategyIdentifierTag must be a positive integer (>=1).",
    "DOC-04": "Strategies/@versionIdentifierTag, @draftFlagIdentifierTag must be positive integers when present.",
    "DOC-05": "Strategies/@tag957Support must be boolean ('true'/'false') when present.",
    "DOC-06": "Strategies/@changeStrategyOnCxlRpl must be boolean when present.",
    "DOC-07": "Strategies must contain at least one <Strategy>.",
    # ---- strategy ----
    "STR-01": "Strategy/@name is required and must match StringID pattern [A-Za-z][A-Za-z0-9_]{0,255}.",
    "STR-02": "Strategy/@name must be unique within the document.",
    "STR-03": "Strategy/@wireValue is required.",
    "STR-04": "Strategy/@version is required.",
    "STR-05": "Strategy/@fixMsgType, when present, must be one of D, E, AB, s.",
    # ---- parameter ----
    "PARAM-01": "Parameter/@name is required and must match pattern [A-Za-z][A-Za-z0-9_]{0,255}.",
    "PARAM-02": "Parameter/@name must be unique within its strategy.",
    "PARAM-03": "Parameter/@xsi:type is required and must be a valid FIXatdl parameter type.",
    "PARAM-04": "Parameter/@use, when present, must be 'optional' or 'required'.",
    "PARAM-05": "minValue/maxValue are only applicable to numeric, date or time parameter types.",
    "PARAM-06": "minValue must be <= maxValue for numeric parameter types.",
    "PARAM-07": "minLength/maxLength are only applicable to String_t, Data_t, MultipleCharValue_t, MultipleStringValue_t.",
    "PARAM-08": "Parameter/@localMktTz is only applicable to UTCTimestamp_t and must be a valid Olson timezone.",
    "PARAM-09": "Parameter/@multiplyBy100 is only applicable to Percentage_t and must be boolean.",
    "PARAM-10": "Parameter/@invertOnWire is only applicable to MultipleCharValue_t / MultipleStringValue_t.",
    "PARAM-11": "Parameter/@precision is only applicable to Float_t, Price_t, PriceOffset_t, Qty_t.",
    "PARAM-12": "Parameter/@trueWireValue & @falseWireValue are only applicable to Boolean_t (and are deprecated).",
    "PARAM-13": "Parameter/@fixTag must be a positive integer when present.",
    "PARAM-14": "Parameter/@constValue, @minValue, @maxValue must match the datatype implied by xsi:type.",
    "PARAM-15": "Parameter boolean attributes (definedByFIX, mutableOnCxlRpl, revertOnCxlRpl) must be boolean.",
    "PARAM-16": "If fixTag is absent the parameter cannot be transported unless Strategies/@tag957Support='true'.",
    # ---- enum pair ----
    "ENUM-01": "EnumPair/@enumID is required and must match StringID pattern [A-Za-z][A-Za-z0-9_]{0,255}.",
    "ENUM-02": "EnumPair/@wireValue is required.",
    "ENUM-03": "EnumPair/@enumID must be unique within its parameter.",
    # ---- edit (validation & flow control) ----
    "EDIT-01": "Edit/@operator and Edit/@logicOperator are mutually exclusive (spec dependency #1).",
    "EDIT-02": "Edit must define exactly one of @operator or @logicOperator.",
    "EDIT-03": "Edit/@field2 and Edit/@value are mutually exclusive (spec dependency #2).",
    "EDIT-04": "Edit/@operator must be one of EX, NX, EQ, LT, GT, NE, LE, GE.",
    "EDIT-05": "Edit/@logicOperator must be one of AND, OR, XOR, NOT.",
    "EDIT-06": "Edit/@field is required when @operator is defined.",
    "EDIT-07": "Edit with operator in {EQ,LT,GT,NE,LE,GE} requires @field2 or @value.",
    "EDIT-08": "An Edit that has child Edits must use @logicOperator and must not use @operator (spec dependency #6).",
    "EDIT-09": "An Edit with @logicOperator must contain child Edit/EditRef operand(s).",
    "EDIT-10": "In a StrategyEdit, Edit/@field & @field2 must name a declared Parameter or a 'FIX_'-prefixed standard field (spec dependency #4).",
    "EDIT-11": "In a StateRule, Edit/@field & @field2 must reference a Control ID in the same strategy.",
    "EDIT-12": "An Edit that is a direct child of <Strategy> or <Strategies> must declare an @id.",
    # ---- edit ref ----
    "EREF-01": "EditRef/@id is required and must reference an Edit declared at strategy or strategies level.",
    # ---- strategy edit ----
    "SEDIT-01": "StrategyEdit/@errorMessage is required.",
    "SEDIT-02": "StrategyEdit must contain exactly one Edit or EditRef.",
    # ---- state rule ----
    "SRULE-01": "StateRule must contain exactly one child Edit.",
    "SRULE-02": "StateRule/@enabled and @visible must be boolean when present.",
    # ---- control ----
    "CTRL-01": "Control/@ID is required and must be unique within its strategy.",
    "CTRL-02": "Control/@xsi:type is required and must be a valid FIXatdl control type.",
    "CTRL-03": "Control/@parameterRef must reference a Parameter name in the same strategy (spec dependency #8).",
    "CTRL-04": "Each ListItem/@enumID must match exactly one EnumPair/@enumID of the bound Parameter (spec dependency #9).",
    "CTRL-05": "checkedEnumRef/uncheckedEnumRef require parameterRef and must match an EnumPair/@enumID (spec dependency #10).",
    "CTRL-06": "Control/@initFixField is required when initPolicy='UseFixField'.",
    "CTRL-07": "Control/@localMktTz is required when a Clock_t control supplies @initValue.",
    "CTRL-08": "Control/@initPolicy must be 'UseValue' or 'UseFixField' when present.",
    "CTRL-09": "Type-specific control attributes must only appear on the applicable xsi:type.",
    "CTRL-10": "ListItem/@uiRep is required; ListItem/@enumID is required when the Control has a parameterRef.",
    # ---- layout ----
    "LAY-01": "StrategyLayout must contain exactly one StrategyPanel.",
    "LAY-02": "A StrategyPanel must not contain both Control and StrategyPanel children (spec dependency #3).",
    "LAY-03": "StrategyPanel/@orientation must be HORIZONTAL or VERTICAL; @border must be None or Line.",
    "LAY-04": "StrategyPanel/@collapsible and @collapsed must be boolean when present.",
    # ---- geographic scope ----
    "GEO-01": "Region/@name must be TheAmericas, EuropeMiddleEastAfrica or AsiaPacificJapan.",
    "GEO-02": "@inclusion (Region/Country/Market/SecurityType) must be 'Include' or 'Exclude'.",
    "GEO-03": "Country/@CountryCode must match ISO 3166-1 alpha-2 pattern [A-Z0-9]{2}.",
    "GEO-04": "Market/@MICCode is required (ISO 10383 Market Identifier Code).",
    # ---- repeating group ----
    "RG-01": "RepeatingGroup/@minSize is required and must be an integer.",
    "RG-02": "RepeatingGroup/@fixTag, when present, must be 555 (NoLegs) or 68 (TotNoOrders).",
    "RG-03": "RepeatingGroup/@name, when present, must be 'TotNoOrders' or 'NoLegs'.",
    "RG-04": "RepeatingGroup must contain at least one Parameter.",
}


# ---------------------------------------------------------------------------
# Controlled vocabularies (from the schema files / specification tables)
# ---------------------------------------------------------------------------
PARAMETER_TYPES = frozenset({
    "Amt_t", "Boolean_t", "Char_t", "Country_t", "Currency_t", "Data_t",
    "Exchange_t", "Float_t", "Int_t", "Language_t", "Length_t",
    "LocalMktDate_t", "MonthYear_t", "MultipleCharValue_t",
    "MultipleStringValue_t", "NumInGroup_t", "Percentage_t", "Price_t",
    "PriceOffset_t", "Qty_t", "SeqNum_t", "String_t", "TagNum_t", "Tenor_t",
    "TZTimeOnly_t", "TZTimestamp_t", "UTCDateOnly_t", "UTCTimeOnly_t",
    "UTCTimestamp_t",
})

CONTROL_TYPES = frozenset({
    "CheckBox_t", "CheckBoxList_t", "Clock_t", "DoubleSpinner_t",
    "DropDownList_t", "EditableDropDownList_t", "HiddenField_t", "Label_t",
    "MultiSelectList_t", "RadioButton_t", "RadioButtonList_t",
    "SingleSelectList_t", "SingleSpinner_t", "Slider_t", "TextField_t",
})

OPERATORS = frozenset({"EX", "NX", "EQ", "LT", "GT", "NE", "LE", "GE"})
COMPARISON_OPERATORS = frozenset({"EQ", "LT", "GT", "NE", "LE", "GE"})
LOGIC_OPERATORS = frozenset({"AND", "OR", "XOR", "NOT"})
INCLUSIONS = frozenset({"Include", "Exclude"})
REGION_NAMES = frozenset({"TheAmericas", "EuropeMiddleEastAfrica", "AsiaPacificJapan"})
FIX_MSG_TYPES = frozenset({"D", "E", "AB", "s"})
USE_VALUES = frozenset({"optional", "required"})
ORIENTATIONS = frozenset({"HORIZONTAL", "VERTICAL"})
BORDERS = frozenset({"None", "Line"})
INIT_POLICIES = frozenset({"UseValue", "UseFixField"})
INCREMENT_POLICIES = frozenset({"LotSize", "Tick"})  # schema omits "Static"
RG_FIXTAGS = frozenset({"555", "68"})
RG_NAMES = frozenset({"TotNoOrders", "NoLegs"})

# Which parameter types accept minValue / maxValue (extended-attribute tables).
MINMAX_TYPES = frozenset({
    "Amt_t", "Float_t", "Int_t", "LocalMktDate_t", "MonthYear_t",
    "Percentage_t", "Price_t", "PriceOffset_t", "Qty_t", "TZTimeOnly_t",
    "TZTimestamp_t", "UTCDateOnly_t", "UTCTimeOnly_t", "UTCTimestamp_t",
})
# Parameter types for which min/max are numerically ordered (comparable as float).
NUMERIC_TYPES = frozenset({
    "Amt_t", "Float_t", "Int_t", "Percentage_t", "Price_t", "PriceOffset_t",
    "Qty_t",
})
LENGTH_TYPES = frozenset({
    "String_t", "Data_t", "MultipleCharValue_t", "MultipleStringValue_t",
})
PRECISION_TYPES = frozenset({"Float_t", "Price_t", "PriceOffset_t", "Qty_t"})

# Datatype implied by xsi:type for the constValue / minValue / maxValue attrs.
PARAM_VALUE_DATATYPE = {
    "Amt_t": "decimal", "Boolean_t": "boolean", "Char_t": "char",
    "Country_t": "country", "Currency_t": "currency", "Data_t": "string",
    "Exchange_t": "exchange", "Float_t": "decimal", "Int_t": "int",
    "Language_t": "language", "Length_t": "posint", "LocalMktDate_t": "date",
    "MonthYear_t": "monthyear", "MultipleCharValue_t": "string",
    "MultipleStringValue_t": "string", "NumInGroup_t": "posint",
    "Percentage_t": "decimal", "Price_t": "decimal", "PriceOffset_t": "decimal",
    "Qty_t": "decimal", "SeqNum_t": "posint", "String_t": "string",
    "TagNum_t": "posint", "Tenor_t": "tenor", "TZTimeOnly_t": "time",
    "TZTimestamp_t": "time", "UTCDateOnly_t": "utcdateonly",
    "UTCTimeOnly_t": "time", "UTCTimestamp_t": "time",
}

# Control attributes that are only valid for specific xsi:type values
# (from the "Control Type-Attribute Matrix").
CONTROL_TYPE_ATTRS = {
    "checkedEnumRef": {"CheckBox_t", "RadioButton_t"},
    "uncheckedEnumRef": {"CheckBox_t", "RadioButton_t"},
    "increment": {"SingleSpinner_t", "Slider_t"},
    "incrementPolicy": {"SingleSpinner_t", "Slider_t"},
    "initValueMode": {"Clock_t"},
    "innerIncrement": {"DoubleSpinner_t"},
    "innerIncrementPolicy": {"DoubleSpinner_t"},
    "outerIncrement": {"DoubleSpinner_t"},
    "outerIncrementPolicy": {"DoubleSpinner_t"},
    "localMktTz": {"Clock_t"},
    "orientation": {"RadioButtonList_t", "CheckBoxList_t"},
    "radioGroup": {"RadioButton_t"},
}

# Olson / zoneinfo timezone identifiers permitted by localMktTz
# (verbatim from fixatdl-timezones-1-1.xsd).
_OLSON_TIMEZONES = frozenset({
    'Africa/Abidjan', 'Africa/Accra', 'Africa/Addis_Ababa', 'Africa/Algiers', 'Africa/Asmara',
    'Africa/Bamako', 'Africa/Bangui', 'Africa/Banjul', 'Africa/Bissau', 'Africa/Blantyre',
    'Africa/Brazzaville', 'Africa/Bujumbura', 'Africa/Cairo', 'Africa/Casablanca', 'Africa/Ceuta',
    'Africa/Conakry', 'Africa/Dakar', 'Africa/Dar_es_Salaam', 'Africa/Djibouti', 'Africa/Douala',
    'Africa/El_Aaiun', 'Africa/Freetown', 'Africa/Gaborone', 'Africa/Harare', 'Africa/Johannesburg',
    'Africa/Kampala', 'Africa/Khartoum', 'Africa/Kigali', 'Africa/Kinshasa', 'Africa/Lagos',
    'Africa/Libreville', 'Africa/Lome', 'Africa/Luanda', 'Africa/Lubumbashi', 'Africa/Lusaka',
    'Africa/Malabo', 'Africa/Maputo', 'Africa/Maseru', 'Africa/Mbabane', 'Africa/Mogadishu',
    'Africa/Monrovia', 'Africa/Nairobi', 'Africa/Ndjamena', 'Africa/Niamey', 'Africa/Nouakchott',
    'Africa/Ouagadougou', 'Africa/Porto-Novo', 'Africa/Sao_Tome', 'Africa/Tripoli', 'Africa/Tunis',
    'Africa/Windhoek', 'America/Adak', 'America/Anchorage', 'America/Anguilla', 'America/Antigua',
    'America/Araguaina', 'America/Argentina/Buenos_Aires', 'America/Argentina/Catamarca',
    'America/Argentina/Cordoba', 'America/Argentina/Jujuy', 'America/Argentina/La_Rioja',
    'America/Argentina/Mendoza', 'America/Argentina/Rio_Gallegos', 'America/Argentina/Salta',
    'America/Argentina/San_Juan', 'America/Argentina/San_Luis', 'America/Argentina/Tucuman',
    'America/Argentina/Ushuaia', 'America/Aruba', 'America/Asuncion', 'America/Atikokan', 'America/Bahia',
    'America/Barbados', 'America/Belem', 'America/Belize', 'America/Blanc-Sablon', 'America/Boa_Vista',
    'America/Bogota', 'America/Boise', 'America/Cambridge_Bay', 'America/Campo_Grande', 'America/Cancun',
    'America/Caracas', 'America/Cayenne', 'America/Cayman', 'America/Chicago', 'America/Chihuahua',
    'America/Costa_Rica', 'America/Cuiaba', 'America/Curacao', 'America/Danmarkshavn', 'America/Dawson',
    'America/Dawson_Creek', 'America/Denver', 'America/Detroit', 'America/Dominica', 'America/Edmonton',
    'America/Eirunepe', 'America/El_Salvador', 'America/Fortaleza', 'America/Glace_Bay', 'America/Godthab',
    'America/Goose_Bay', 'America/Grand_Turk', 'America/Grenada', 'America/Guadeloupe', 'America/Guatemala',
    'America/Guayaquil', 'America/Guyana', 'America/Halifax', 'America/Havana', 'America/Hermosillo',
    'America/Indiana/Indianapolis', 'America/Indiana/Knox', 'America/Indiana/Marengo',
    'America/Indiana/Petersburg', 'America/Indiana/Tell_City', 'America/Indiana/Vevay',
    'America/Indiana/Vincennes', 'America/Indiana/Winamac', 'America/Inuvik', 'America/Iqaluit',
    'America/Jamaica', 'America/Juneau', 'America/Kentucky/Louisville', 'America/Kentucky/Monticello',
    'America/La_Paz', 'America/Lima', 'America/Los_Angeles', 'America/Maceio', 'America/Managua',
    'America/Manaus', 'America/Marigot', 'America/Martinique', 'America/Mazatlan', 'America/Menominee',
    'America/Merida', 'America/Mexico_City', 'America/Miquelon', 'America/Moncton', 'America/Monterrey',
    'America/Montevideo', 'America/Montreal', 'America/Montserrat', 'America/Nassau', 'America/New_York',
    'America/Nipigon', 'America/Nome', 'America/Noronha', 'America/North_Dakota/Center',
    'America/North_Dakota/New_Salem', 'America/Panama', 'America/Pangnirtung', 'America/Paramaribo',
    'America/Phoenix', 'America/Port-au-Prince', 'America/Port_of_Spain', 'America/Porto_Velho',
    'America/Puerto_Rico', 'America/Rainy_River', 'America/Rankin_Inlet', 'America/Recife', 'America/Regina',
    'America/Resolute', 'America/Rio_Branco', 'America/Santarem', 'America/Santiago', 'America/Santo_Domingo',
    'America/Sao_Paulo', 'America/Scoresbysund', 'America/Shiprock', 'America/St_Barthelemy',
    'America/St_Johns', 'America/St_Kitts', 'America/St_Lucia', 'America/St_Thomas', 'America/St_Vincent',
    'America/Swift_Current', 'America/Tegucigalpa', 'America/Thule', 'America/Thunder_Bay', 'America/Tijuana',
    'America/Toronto', 'America/Tortola', 'America/Vancouver', 'America/Whitehorse', 'America/Winnipeg',
    'America/Yakutat', 'America/Yellowknife', 'Antarctica/Casey', 'Antarctica/Davis',
    'Antarctica/DumontDUrville', 'Antarctica/Mawson', 'Antarctica/McMurdo', 'Antarctica/Palmer',
    'Antarctica/Rothera', 'Antarctica/South_Pole', 'Antarctica/Syowa', 'Antarctica/Vostok',
    'Arctic/Longyearbyen', 'Asia/Aden', 'Asia/Almaty', 'Asia/Amman', 'Asia/Anadyr', 'Asia/Aqtau',
    'Asia/Aqtobe', 'Asia/Ashgabat', 'Asia/Baghdad', 'Asia/Bahrain', 'Asia/Baku', 'Asia/Bangkok',
    'Asia/Beirut', 'Asia/Bishkek', 'Asia/Brunei', 'Asia/Choibalsan', 'Asia/Chongqing', 'Asia/Colombo',
    'Asia/Damascus', 'Asia/Dhaka', 'Asia/Dili', 'Asia/Dubai', 'Asia/Dushanbe', 'Asia/Gaza', 'Asia/Harbin',
    'Asia/Ho_Chi_Minh', 'Asia/Hong_Kong', 'Asia/Hovd', 'Asia/Irkutsk', 'Asia/Jakarta', 'Asia/Jayapura',
    'Asia/Jerusalem', 'Asia/Kabul', 'Asia/Kamchatka', 'Asia/Karachi', 'Asia/Kashgar', 'Asia/Katmandu',
    'Asia/Kolkata', 'Asia/Krasnoyarsk', 'Asia/Kuala_Lumpur', 'Asia/Kuching', 'Asia/Kuwait', 'Asia/Macau',
    'Asia/Magadan', 'Asia/Makassar', 'Asia/Manila', 'Asia/Muscat', 'Asia/Nicosia', 'Asia/Novosibirsk',
    'Asia/Omsk', 'Asia/Oral', 'Asia/Phnom_Penh', 'Asia/Pontianak', 'Asia/Pyongyang', 'Asia/Qatar',
    'Asia/Qyzylorda', 'Asia/Rangoon', 'Asia/Riyadh', 'Asia/Sakhalin', 'Asia/Samarkand', 'Asia/Seoul',
    'Asia/Shanghai', 'Asia/Singapore', 'Asia/Taipei', 'Asia/Tashkent', 'Asia/Tbilisi', 'Asia/Tehran',
    'Asia/Thimphu', 'Asia/Tokyo', 'Asia/Ulaanbaatar', 'Asia/Urumqi', 'Asia/Vientiane', 'Asia/Vladivostok',
    'Asia/Yakutsk', 'Asia/Yekaterinburg', 'Asia/Yerevan', 'Atlantic/Azores', 'Atlantic/Bermuda',
    'Atlantic/Canary', 'Atlantic/Cape_Verde', 'Atlantic/Faroe', 'Atlantic/Madeira', 'Atlantic/Reykjavik',
    'Atlantic/South_Georgia', 'Atlantic/St_Helena', 'Atlantic/Stanley', 'Australia/Adelaide',
    'Australia/Brisbane', 'Australia/Broken_Hill', 'Australia/Currie', 'Australia/Darwin', 'Australia/Eucla',
    'Australia/Hobart', 'Australia/Lindeman', 'Australia/Lord_Howe', 'Australia/Melbourne', 'Australia/Perth',
    'Australia/Sydney', 'Europe/Amsterdam', 'Europe/Andorra', 'Europe/Athens', 'Europe/Belgrade',
    'Europe/Berlin', 'Europe/Bratislava', 'Europe/Brussels', 'Europe/Bucharest', 'Europe/Budapest',
    'Europe/Chisinau', 'Europe/Copenhagen', 'Europe/Dublin', 'Europe/Gibraltar', 'Europe/Guernsey',
    'Europe/Helsinki', 'Europe/Isle_of_Man', 'Europe/Istanbul', 'Europe/Jersey', 'Europe/Kaliningrad',
    'Europe/Kiev', 'Europe/Lisbon', 'Europe/Ljubljana', 'Europe/London', 'Europe/Luxembourg', 'Europe/Madrid',
    'Europe/Malta', 'Europe/Mariehamn', 'Europe/Minsk', 'Europe/Monaco', 'Europe/Moscow', 'Europe/Oslo',
    'Europe/Paris', 'Europe/Podgorica', 'Europe/Prague', 'Europe/Riga', 'Europe/Rome', 'Europe/Samara',
    'Europe/San_Marino', 'Europe/Sarajevo', 'Europe/Simferopol', 'Europe/Skopje', 'Europe/Sofia',
    'Europe/Stockholm', 'Europe/Tallinn', 'Europe/Tirane', 'Europe/Uzhgorod', 'Europe/Vaduz',
    'Europe/Vatican', 'Europe/Vienna', 'Europe/Vilnius', 'Europe/Volgograd', 'Europe/Warsaw', 'Europe/Zagreb',
    'Europe/Zaporozhye', 'Europe/Zurich', 'Indian/Antananarivo', 'Indian/Chagos', 'Indian/Christmas',
    'Indian/Cocos', 'Indian/Comoro', 'Indian/Kerguelen', 'Indian/Mahe', 'Indian/Maldives', 'Indian/Mauritius',
    'Indian/Mayotte', 'Indian/Reunion', 'Pacific/Apia', 'Pacific/Auckland', 'Pacific/Chatham',
    'Pacific/Easter', 'Pacific/Efate', 'Pacific/Enderbury', 'Pacific/Fakaofo', 'Pacific/Fiji',
    'Pacific/Funafuti', 'Pacific/Galapagos', 'Pacific/Gambier', 'Pacific/Guadalcanal', 'Pacific/Guam',
    'Pacific/Honolulu', 'Pacific/Johnston', 'Pacific/Kiritimati', 'Pacific/Kosrae', 'Pacific/Kwajalein',
    'Pacific/Majuro', 'Pacific/Marquesas', 'Pacific/Midway', 'Pacific/Nauru', 'Pacific/Niue',
    'Pacific/Norfolk', 'Pacific/Noumea', 'Pacific/Pago_Pago', 'Pacific/Palau', 'Pacific/Pitcairn',
    'Pacific/Ponape', 'Pacific/Port_Moresby', 'Pacific/Rarotonga', 'Pacific/Saipan', 'Pacific/Tahiti',
    'Pacific/Tarawa', 'Pacific/Tongatapu', 'Pacific/Truk', 'Pacific/Wake', 'Pacific/Wallis'
})


# ---------------------------------------------------------------------------
# Datatype value validators
# ---------------------------------------------------------------------------
_STRINGID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,255}$")
_INT_RE = re.compile(r"^[+-]?\d+$")
_DECIMAL_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}(:\d{2})?)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UTCDATEONLY_RE = re.compile(r"^\d{8}$")
_MONTHYEAR_RE = re.compile(r"^\d{4}(0[1-9]|1[0-2])((0[1-9]|[12]\d|3[01])|w[1-5])?$")
_TENOR_RE = re.compile(r"^[DMWY]\d+$")
_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")
_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")
_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2}$")
_COUNTRYCODE_RE = re.compile(r"^[A-Z0-9]{2}$")
_BOOLEANS = frozenset({"true", "false", "0", "1"})


def _is_int(v):
    return bool(_INT_RE.match(v))


def _is_posint(v):
    return bool(_INT_RE.match(v)) and int(v) >= 1


def _is_decimal(v):
    return bool(_DECIMAL_RE.match(v))


def _check_datatype(value, datatype):
    """Return True if `value` is a syntactically valid instance of `datatype`."""
    v = value.strip()
    if datatype == "int":
        return _is_int(v)
    if datatype == "posint":
        return _is_posint(v)
    if datatype == "decimal":
        return _is_decimal(v)
    if datatype == "boolean":
        return v in _BOOLEANS
    if datatype == "char":
        return len(value) == 1
    if datatype == "time":
        return bool(_TIME_RE.match(v))
    if datatype == "date":
        return bool(_DATE_RE.match(v))
    if datatype == "utcdateonly":
        return bool(_UTCDATEONLY_RE.match(v))
    if datatype == "monthyear":
        return bool(_MONTHYEAR_RE.match(v))
    if datatype == "tenor":
        return bool(_TENOR_RE.match(v))
    if datatype == "country":
        return bool(_COUNTRY_RE.match(v))
    if datatype == "currency":
        return bool(_CURRENCY_RE.match(v))
    if datatype == "language":
        return bool(_LANGUAGE_RE.match(v))
    if datatype == "exchange":
        return len(v) > 0
    if datatype == "string":
        return True
    return True


# ---------------------------------------------------------------------------
# Line-number-aware XML parsing (stdlib expat, namespace-transparent)
# ---------------------------------------------------------------------------
class ParseError(Exception):
    def __init__(self, message, line):
        super().__init__(message)
        self.message = message
        self.line = line


def _local(name):
    """Strip namespace prefix/URI, returning the local element/attribute name."""
    if "}" in name:
        name = name.rsplit("}", 1)[-1]
    if ":" in name:
        name = name.rsplit(":", 1)[-1]
    return name


def parse_xml(text):
    """
    Parse `text` into an ElementTree tree plus a {id(elem): line} map.

    Parsing is namespace-transparent: element tags and attribute keys are
    reduced to their local names, so documents using either the
    'FIXatdl-1-1' or the legacy 'ATDL-1-1' namespace URIs validate identically.
    The xsi:type attribute is exposed under the key 'xsi:type' (its prefix is
    stripped from the *value* when interpreted).
    """
    lines = {}
    stack = []
    root_holder = []
    parser = expat.ParserCreate()

    def start(name, attrs):
        tag = _local(name)
        attrib = {}
        for k, v in attrs.items():
            if k == "xmlns" or k.startswith("xmlns:"):
                continue
            # Preserve xsi:type explicitly; otherwise key by local name.
            if k.endswith(":type") and ("xsi" in k or "XMLSchema-instance" in k):
                attrib["xsi:type"] = v
            else:
                attrib[_local(k)] = v
        elem = ET.Element(tag, attrib)
        lines[id(elem)] = parser.CurrentLineNumber
        if stack:
            stack[-1].append(elem)
        else:
            root_holder.append(elem)
        stack.append(elem)

    def end(name):
        if stack:
            stack.pop()

    parser.StartElementHandler = start
    parser.EndElementHandler = end

    try:
        parser.Parse(text, True)
    except expat.ExpatError as exc:
        raise ParseError(expat.ErrorString(exc.code), exc.lineno) from exc

    if not root_holder:
        raise ParseError("Document contains no root element.", 1)
    return root_holder[0], lines


def _xsitype(elem):
    """Return the local (prefix-stripped) xsi:type value, or None."""
    raw = elem.get("xsi:type") or elem.get("type")
    if raw is None:
        return None
    return raw.rsplit(":", 1)[-1].strip()


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------
class _Validator:
    def __init__(self, lines):
        self._lines = lines
        self.findings = []

    # -- finding helpers ----------------------------------------------------
    def _add(self, rule_id, severity, elem, message, attribute=None):
        self.findings.append({
            "rule_id": rule_id,
            "severity": severity,
            "element": elem.tag if elem is not None else None,
            "attribute": attribute,
            "line": self._lines.get(id(elem)) if elem is not None else None,
            "message": message,
        })

    def error(self, rule_id, elem, message, attribute=None):
        self._add(rule_id, "error", elem, message, attribute)

    def warn(self, rule_id, elem, message, attribute=None):
        self._add(rule_id, "warning", elem, message, attribute)

    # -- bool helper --------------------------------------------------------
    def _check_bool(self, elem, attr, rule_id):
        v = elem.get(attr)
        if v is not None and v not in _BOOLEANS:
            self.error(rule_id, elem,
                       f"@{attr}='{v}' is not a boolean ('true'/'false').", attr)

    # -- top-level ----------------------------------------------------------
    def validate(self, root):
        if root.tag != "Strategies":
            self.error("DOC-01", root,
                       f"Root element is <{root.tag}>; expected <Strategies>.")
            return  # nothing else makes sense

        # DOC-02 / DOC-03 strategyIdentifierTag
        sid = root.get("strategyIdentifierTag")
        if sid is None:
            self.error("DOC-02", root, "Required attribute @strategyIdentifierTag is missing.",
                       "strategyIdentifierTag")
        elif not _is_posint(sid):
            self.error("DOC-03", root,
                       f"@strategyIdentifierTag='{sid}' must be a positive integer.",
                       "strategyIdentifierTag")

        # DOC-04 other tag attributes
        for attr in ("versionIdentifierTag", "draftFlagIdentifierTag"):
            v = root.get(attr)
            if v is not None and not _is_posint(v):
                self.error("DOC-04", root,
                           f"@{attr}='{v}' must be a positive integer.", attr)

        # DOC-05 / DOC-06 booleans
        self._check_bool(root, "tag957Support", "DOC-05")
        self._check_bool(root, "changeStrategyOnCxlRpl", "DOC-06")

        tag957 = (root.get("tag957Support") or "false").strip().lower() in ("true", "1")

        # Strategies-level Edit ids (global scope) -- collect for EditRef/ EDIT-12
        strategies_edit_ids = set()
        for edit in root.findall("Edit"):
            eid = edit.get("id")
            if eid is None:
                self.error("EDIT-12", edit,
                           "Edit declared directly under <Strategies> must have an @id.")
            else:
                strategies_edit_ids.add(eid)

        strategies = root.findall("Strategy")
        if not strategies:
            self.error("DOC-07", root, "<Strategies> contains no <Strategy> elements.")

        seen_names = set()
        for strat in strategies:
            name = strat.get("name")
            if name is not None:
                if name in seen_names:
                    self.error("STR-02", strat,
                               f"Duplicate Strategy/@name '{name}'.", "name")
                seen_names.add(name)
            self._validate_strategy(strat, tag957, strategies_edit_ids)

    # -- strategy -----------------------------------------------------------
    def _validate_strategy(self, strat, tag957_support, strategies_edit_ids):
        name = strat.get("name")
        if name is None:
            self.error("STR-01", strat, "Strategy/@name is required.", "name")
        elif not _STRINGID_RE.match(name):
            self.error("STR-01", strat,
                       f"Strategy/@name '{name}' violates StringID pattern.", "name")
        if strat.get("wireValue") is None:
            self.error("STR-03", strat, "Strategy/@wireValue is required.", "wireValue")
        if strat.get("version") is None:
            self.error("STR-04", strat, "Strategy/@version is required.", "version")
        msgtype = strat.get("fixMsgType")
        if msgtype is not None and msgtype not in FIX_MSG_TYPES:
            self.error("STR-05", strat,
                       f"Strategy/@fixMsgType='{msgtype}' is not one of {sorted(FIX_MSG_TYPES)}.",
                       "fixMsgType")

        # ---- collect parameter scope ----
        params = {}          # name -> {type, enumIDs:set, has_enum:bool}
        param_seen = set()
        for p in strat.iter("Parameter"):
            pname = p.get("name")
            ptype = _xsitype(p)
            enum_ids = set()
            for ep in p.findall("EnumPair"):
                eid = ep.get("enumID")
                if eid:
                    enum_ids.add(eid)
            if pname is not None:
                if pname in param_seen:
                    self.error("PARAM-02", p,
                               f"Duplicate Parameter/@name '{pname}' within strategy.", "name")
                param_seen.add(pname)
                params[pname] = {"type": ptype, "enumIDs": enum_ids,
                                 "has_enum": bool(enum_ids)}

        # ---- validate each parameter ----
        for p in strat.iter("Parameter"):
            self._validate_parameter(p, tag957_support)

        # ---- collect control ids + strategy-level edit ids ----
        control_ids = set()
        for c in strat.iter("Control"):
            cid = c.get("ID")
            if cid:
                control_ids.add(cid)
        strategy_edit_ids = set(strategies_edit_ids)
        for edit in strat.findall("Edit"):
            eid = edit.get("id")
            if eid is None:
                self.error("EDIT-12", edit,
                           "Edit declared directly under <Strategy> must have an @id.")
            else:
                strategy_edit_ids.add(eid)

        # ---- control uniqueness ----
        seen_ctrl = set()
        for c in strat.iter("Control"):
            cid = c.get("ID")
            if cid is None:
                self.error("CTRL-01", c, "Control/@ID is required.", "ID")
            elif cid in seen_ctrl:
                self.error("CTRL-01", c, f"Duplicate Control/@ID '{cid}'.", "ID")
            else:
                seen_ctrl.add(cid)

        # ---- validation rules (StrategyEdit) ----
        for se in strat.findall("StrategyEdit"):
            self._validate_strategy_edit(se, params, strategy_edit_ids)

        # ---- geographic scope ----
        self._validate_scope(strat)

        # ---- repeating groups ----
        for rg in strat.findall("RepeatingGroup"):
            self._validate_repeating_group(rg)

        # ---- layout / controls ----
        layouts = strat.findall("StrategyLayout")
        for layout in layouts:
            self._validate_layout(layout, params, control_ids, strategy_edit_ids)

    # -- parameter ----------------------------------------------------------
    def _validate_parameter(self, p, tag957_support):
        name = p.get("name")
        if name is None:
            self.error("PARAM-01", p, "Parameter/@name is required.", "name")
        elif not _STRINGID_RE.match(name):
            self.error("PARAM-01", p,
                       f"Parameter/@name '{name}' violates pattern [A-Za-z][A-Za-z0-9_]{{0,255}}.",
                       "name")

        ptype = _xsitype(p)
        if ptype is None:
            self.error("PARAM-03", p, "Parameter/@xsi:type is required.", "xsi:type")
        elif ptype not in PARAMETER_TYPES:
            self.error("PARAM-03", p,
                       f"Parameter/@xsi:type='{ptype}' is not a valid FIXatdl parameter type.",
                       "xsi:type")

        use = p.get("use")
        if use is not None and use not in USE_VALUES:
            self.error("PARAM-04", p,
                       f"Parameter/@use='{use}' must be 'optional' or 'required'.", "use")

        # min/max applicability + datatype + ordering
        has_min = p.get("minValue") is not None
        has_max = p.get("maxValue") is not None
        if (has_min or has_max) and ptype not in MINMAX_TYPES:
            self.error("PARAM-05", p,
                       f"minValue/maxValue are not applicable to xsi:type '{ptype}'.",
                       "minValue" if has_min else "maxValue")
        dt = PARAM_VALUE_DATATYPE.get(ptype)
        for attr in ("minValue", "maxValue", "constValue"):
            v = p.get(attr)
            if v is not None and dt is not None and not _check_datatype(v, dt):
                self.error("PARAM-14", p,
                           f"Parameter/@{attr}='{v}' is not a valid {dt} value for xsi:type '{ptype}'.",
                           attr)
        if has_min and has_max and ptype in NUMERIC_TYPES:
            try:
                if float(p.get("minValue")) > float(p.get("maxValue")):
                    self.error("PARAM-06", p,
                               f"minValue ({p.get('minValue')}) is greater than maxValue ({p.get('maxValue')}).",
                               "minValue")
            except ValueError:
                pass

        # length applicability
        if (p.get("minLength") is not None or p.get("maxLength") is not None) \
                and ptype not in LENGTH_TYPES:
            self.error("PARAM-07", p,
                       f"minLength/maxLength are not applicable to xsi:type '{ptype}'.",
                       "maxLength")

        # localMktTz
        tz = p.get("localMktTz")
        if tz is not None:
            if ptype != "UTCTimestamp_t":
                self.error("PARAM-08", p,
                           f"Parameter/@localMktTz is only applicable to UTCTimestamp_t (got '{ptype}').",
                           "localMktTz")
            elif tz not in _OLSON_TIMEZONES:
                self.error("PARAM-08", p,
                           f"Parameter/@localMktTz='{tz}' is not a recognised Olson timezone.",
                           "localMktTz")

        # multiplyBy100
        if p.get("multiplyBy100") is not None:
            if ptype != "Percentage_t":
                self.error("PARAM-09", p,
                           "Parameter/@multiplyBy100 is only applicable to Percentage_t.",
                           "multiplyBy100")
            else:
                self._check_bool(p, "multiplyBy100", "PARAM-09")

        # invertOnWire
        if p.get("invertOnWire") is not None and ptype not in (
                "MultipleCharValue_t", "MultipleStringValue_t"):
            self.error("PARAM-10", p,
                       "Parameter/@invertOnWire is only applicable to MultipleCharValue_t / MultipleStringValue_t.",
                       "invertOnWire")

        # precision
        if p.get("precision") is not None and ptype not in PRECISION_TYPES:
            self.error("PARAM-11", p,
                       f"Parameter/@precision is not applicable to xsi:type '{ptype}'.",
                       "precision")

        # deprecated boolean wire values
        for attr in ("trueWireValue", "falseWireValue"):
            if p.get(attr) is not None:
                if ptype != "Boolean_t":
                    self.error("PARAM-12", p,
                               f"Parameter/@{attr} is only applicable to Boolean_t.", attr)
                else:
                    self.warn("PARAM-12", p,
                              f"Parameter/@{attr} is deprecated; use Char_t/String_t with EnumPairs instead.",
                              attr)

        # fixTag
        fixtag = p.get("fixTag")
        if fixtag is not None and not _is_posint(fixtag):
            self.error("PARAM-13", p,
                       f"Parameter/@fixTag='{fixtag}' must be a positive integer.", "fixTag")

        # boolean attrs
        for attr in ("definedByFIX", "mutableOnCxlRpl", "revertOnCxlRpl"):
            self._check_bool(p, attr, "PARAM-15")

        # transport: fixTag absent requires tag957Support
        if fixtag is None and p.get("constValue") is None and not tag957_support:
            self.warn("PARAM-16", p,
                      "Parameter has no @fixTag and Strategies/@tag957Support is not 'true'; "
                      "the value cannot be transported over the wire.", "fixTag")

        # EnumPairs
        seen_enum = set()
        for ep in p.findall("EnumPair"):
            eid = ep.get("enumID")
            if eid is None:
                self.error("ENUM-01", ep, "EnumPair/@enumID is required.", "enumID")
            elif not _STRINGID_RE.match(eid):
                self.error("ENUM-01", ep,
                           f"EnumPair/@enumID '{eid}' violates StringID pattern.", "enumID")
            elif eid in seen_enum:
                self.error("ENUM-03", ep,
                           f"Duplicate EnumPair/@enumID '{eid}' within parameter.", "enumID")
            else:
                seen_enum.add(eid)
            if ep.get("wireValue") is None:
                self.error("ENUM-02", ep, "EnumPair/@wireValue is required.", "wireValue")

    # -- strategy edit (validation rule) ------------------------------------
    def _validate_strategy_edit(self, se, params, edit_ids):
        # The schema names this attribute @errorMessage; the spec attribute table
        # uses @errorMsg.  Accept either so real-world documents validate.
        if se.get("errorMessage") is None and se.get("errorMsg") is None:
            self.error("SEDIT-01", se,
                       "StrategyEdit/@errorMessage is required.", "errorMessage")
        edits = se.findall("Edit")
        refs = se.findall("EditRef")
        if len(edits) + len(refs) != 1:
            self.error("SEDIT-02", se,
                       f"StrategyEdit must contain exactly one Edit or EditRef "
                       f"(found {len(edits)} Edit + {len(refs)} EditRef).")
        for ref in refs:
            self._validate_editref(ref, edit_ids)
        for edit in edits:
            self._validate_edit(edit, context="strategyEdit",
                                 params=params, control_ids=None, edit_ids=edit_ids)

    # -- edit ref -----------------------------------------------------------
    def _validate_editref(self, ref, edit_ids):
        rid = ref.get("id")
        if rid is None:
            self.error("EREF-01", ref, "EditRef/@id is required.", "id")
        elif rid not in edit_ids:
            self.error("EREF-01", ref,
                       f"EditRef/@id='{rid}' does not reference any declared Edit/@id.", "id")

    # -- edit (recursive) ---------------------------------------------------
    def _validate_edit(self, edit, context, params, control_ids, edit_ids):
        op = edit.get("operator")
        logic = edit.get("logicOperator")
        child_edits = edit.findall("Edit")
        child_refs = edit.findall("EditRef")
        has_children = bool(child_edits or child_refs)

        # EDIT-01 mutually exclusive
        if op is not None and logic is not None:
            self.error("EDIT-01", edit,
                       "Edit/@operator and Edit/@logicOperator are mutually exclusive.")
        # EDIT-02 exactly one present
        if op is None and logic is None:
            self.error("EDIT-02", edit,
                       "Edit must define either @operator or @logicOperator.")

        # EDIT-04 / EDIT-05 enum membership
        if op is not None and op not in OPERATORS:
            self.error("EDIT-04", edit,
                       f"Edit/@operator='{op}' is not a valid operator.", "operator")
        if logic is not None and logic not in LOGIC_OPERATORS:
            self.error("EDIT-05", edit,
                       f"Edit/@logicOperator='{logic}' is not a valid logical operator.",
                       "logicOperator")

        # EDIT-03 field2/value mutually exclusive
        if edit.get("field2") is not None and edit.get("value") is not None:
            self.error("EDIT-03", edit,
                       "Edit/@field2 and Edit/@value are mutually exclusive.")

        # EDIT-08 parent edit (has children) must use logicOperator, not operator
        if has_children:
            if op is not None:
                self.error("EDIT-08", edit,
                           "An Edit with child Edits must not define @operator.")
            if logic is None:
                self.error("EDIT-08", edit,
                           "An Edit with child Edits must define @logicOperator.")
        # EDIT-09 logicOperator requires operands
        if logic is not None and not has_children:
            self.error("EDIT-09", edit,
                       f"Edit/@logicOperator='{logic}' has no child Edit/EditRef operands.")

        # operator-specific operand requirements
        if op is not None:
            field = edit.get("field")
            if field is None:
                self.error("EDIT-06", edit,
                           "Edit/@field is required when @operator is defined.", "field")
            if op in COMPARISON_OPERATORS and \
                    edit.get("field2") is None and edit.get("value") is None:
                self.error("EDIT-07", edit,
                           f"Edit with operator '{op}' requires @field2 or @value.")

            # field reference resolution (EDIT-10 / EDIT-11)
            for fattr in ("field", "field2"):
                fval = edit.get(fattr)
                if fval is None:
                    continue
                if context == "strategyEdit":
                    if not fval.startswith("FIX_") and fval not in params:
                        self.error("EDIT-10", edit,
                                   f"Edit/@{fattr}='{fval}' is neither a declared Parameter "
                                   f"nor a 'FIX_'-prefixed standard field.", fattr)
                elif context == "stateRule" and control_ids is not None:
                    if not fval.startswith("FIX_") and fval not in control_ids:
                        self.error("EDIT-11", edit,
                                   f"Edit/@{fattr}='{fval}' does not reference a Control ID "
                                   f"in this strategy.", fattr)

        # recurse
        for ref in child_refs:
            self._validate_editref(ref, edit_ids)
        for child in child_edits:
            self._validate_edit(child, context, params, control_ids, edit_ids)

    # -- geographic scope ---------------------------------------------------
    def _validate_scope(self, strat):
        for region in strat.iter("Region"):
            rname = region.get("name")
            if rname is not None and rname not in REGION_NAMES:
                self.error("GEO-01", region,
                           f"Region/@name='{rname}' is not a valid region.", "name")
            self._check_inclusion(region)
            for country in region.findall("Country"):
                self._check_inclusion(country)
                cc = country.get("CountryCode")
                if cc is None:
                    self.error("GEO-03", country, "Country/@CountryCode is required.", "CountryCode")
                elif not _COUNTRYCODE_RE.match(cc):
                    self.error("GEO-03", country,
                               f"Country/@CountryCode='{cc}' violates pattern [A-Z0-9]{{2}}.",
                               "CountryCode")
        for market in strat.iter("Market"):
            self._check_inclusion(market)
            if market.get("MICCode") is None:
                self.error("GEO-04", market, "Market/@MICCode is required.", "MICCode")
        for st in strat.iter("SecurityType"):
            self._check_inclusion(st)

    def _check_inclusion(self, elem):
        inc = elem.get("inclusion")
        if inc is not None and inc not in INCLUSIONS:
            self.error("GEO-02", elem,
                       f"{elem.tag}/@inclusion='{inc}' must be 'Include' or 'Exclude'.",
                       "inclusion")

    # -- repeating group ----------------------------------------------------
    def _validate_repeating_group(self, rg):
        ms = rg.get("minSize")
        if ms is None:
            self.error("RG-01", rg, "RepeatingGroup/@minSize is required.", "minSize")
        elif not _is_int(ms):
            self.error("RG-01", rg,
                       f"RepeatingGroup/@minSize='{ms}' must be an integer.", "minSize")
        ft = rg.get("fixTag")
        if ft is not None and ft not in RG_FIXTAGS:
            self.error("RG-02", rg,
                       f"RepeatingGroup/@fixTag='{ft}' must be 555 (NoLegs) or 68 (TotNoOrders).",
                       "fixTag")
        nm = rg.get("name")
        if nm is not None and nm not in RG_NAMES:
            self.error("RG-03", rg,
                       f"RepeatingGroup/@name='{nm}' must be 'TotNoOrders' or 'NoLegs'.", "name")
        if not rg.findall("Parameter"):
            self.error("RG-04", rg, "RepeatingGroup must contain at least one Parameter.")

    # -- layout -------------------------------------------------------------
    def _validate_layout(self, layout, params, control_ids, edit_ids):
        panels = layout.findall("StrategyPanel")
        if len(panels) == 0:
            self.error("LAY-01", layout, "StrategyLayout must contain a StrategyPanel.")
        elif len(panels) > 1:
            self.warn("LAY-01", layout,
                      f"StrategyLayout contains {len(panels)} StrategyPanels; the specification "
                      "text requires exactly one.")
        for panel in panels:
            self._validate_panel(panel)
        for ctrl in layout.iter("Control"):
            self._validate_control(ctrl, params, control_ids, edit_ids)

    def _validate_panel(self, panel):
        has_control = bool(panel.findall("Control"))
        has_panel = bool(panel.findall("StrategyPanel"))
        if has_control and has_panel:
            self.error("LAY-02", panel,
                       "StrategyPanel must not contain both Control and StrategyPanel children.")
        orient = panel.get("orientation")
        if orient is not None and orient not in ORIENTATIONS:
            self.error("LAY-03", panel,
                       f"StrategyPanel/@orientation='{orient}' must be HORIZONTAL or VERTICAL.",
                       "orientation")
        border = panel.get("border")
        if border is not None and border not in BORDERS:
            self.error("LAY-03", panel,
                       f"StrategyPanel/@border='{border}' must be None or Line.", "border")
        self._check_bool(panel, "collapsible", "LAY-04")
        self._check_bool(panel, "collapsed", "LAY-04")
        # recurse nested panels
        for nested in panel.findall("StrategyPanel"):
            self._validate_panel(nested)

    # -- control ------------------------------------------------------------
    def _validate_control(self, ctrl, params, control_ids, edit_ids):
        if ctrl.get("ID") is None:
            self.error("CTRL-01", ctrl, "Control/@ID is required.", "ID")

        ctype = _xsitype(ctrl)
        if ctype is None:
            self.error("CTRL-02", ctrl, "Control/@xsi:type is required.", "xsi:type")
        elif ctype not in CONTROL_TYPES:
            self.error("CTRL-02", ctrl,
                       f"Control/@xsi:type='{ctype}' is not a valid FIXatdl control type.",
                       "xsi:type")

        # parameterRef resolution (dependency #8)
        pref = ctrl.get("parameterRef")
        bound_param = params.get(pref) if pref is not None else None
        if pref is not None and bound_param is None:
            self.error("CTRL-03", ctrl,
                       f"Control/@parameterRef='{pref}' does not match any Parameter/@name.",
                       "parameterRef")

        # initPolicy / initFixField (CTRL-06, CTRL-08)
        ipolicy = ctrl.get("initPolicy")
        if ipolicy is not None and ipolicy not in INIT_POLICIES:
            self.error("CTRL-08", ctrl,
                       f"Control/@initPolicy='{ipolicy}' must be 'UseValue' or 'UseFixField'.",
                       "initPolicy")
        if ipolicy == "UseFixField" and ctrl.get("initFixField") is None:
            self.error("CTRL-06", ctrl,
                       "Control/@initFixField is required when initPolicy='UseFixField'.",
                       "initFixField")

        # Clock_t localMktTz when initValue supplied (CTRL-07)
        if ctype == "Clock_t" and ctrl.get("initValue") is not None \
                and ctrl.get("localMktTz") is None:
            self.error("CTRL-07", ctrl,
                       "Clock_t control with @initValue must also supply @localMktTz.",
                       "localMktTz")
        ctz = ctrl.get("localMktTz")
        if ctz is not None and ctz not in _OLSON_TIMEZONES:
            self.error("CTRL-07", ctrl,
                       f"Control/@localMktTz='{ctz}' is not a recognised Olson timezone.",
                       "localMktTz")

        # type-specific attribute applicability (CTRL-09)
        for attr, valid_types in CONTROL_TYPE_ATTRS.items():
            if ctrl.get(attr) is not None and ctype is not None and ctype not in valid_types:
                self.error("CTRL-09", ctrl,
                           f"Control/@{attr} is not applicable to xsi:type '{ctype}' "
                           f"(valid for {sorted(valid_types)}).", attr)

        # checkedEnumRef / uncheckedEnumRef (dependency #10)
        for attr in ("checkedEnumRef", "uncheckedEnumRef"):
            ref = ctrl.get(attr)
            if ref is None:
                continue
            if pref is None:
                self.error("CTRL-05", ctrl,
                           f"Control/@{attr} requires @parameterRef to be defined.", attr)
            elif bound_param is not None and ref not in bound_param["enumIDs"]:
                self.error("CTRL-05", ctrl,
                           f"Control/@{attr}='{ref}' does not match any EnumPair/@enumID "
                           f"of parameter '{pref}'.", attr)

        # ListItem handling (dependency #9 + CTRL-10)
        list_items = ctrl.findall("ListItem")
        for li in list_items:
            if li.get("uiRep") is None:
                self.error("CTRL-10", li, "ListItem/@uiRep is required.", "uiRep")
            eid = li.get("enumID")
            if eid is None:
                if pref is not None:
                    self.error("CTRL-10", li,
                               "ListItem/@enumID is required when the Control has a parameterRef.",
                               "enumID")
            elif bound_param is not None:
                if not bound_param["has_enum"]:
                    self.error("CTRL-04", li,
                               f"ListItem/@enumID='{eid}' but bound parameter '{pref}' "
                               "declares no EnumPair elements.", "enumID")
                elif eid not in bound_param["enumIDs"]:
                    self.error("CTRL-04", li,
                               f"ListItem/@enumID='{eid}' does not match any EnumPair/@enumID "
                               f"of parameter '{pref}'.", "enumID")

        # StateRules
        for sr in ctrl.findall("StateRule"):
            self._validate_state_rule(sr, params, control_ids, edit_ids)

    # -- state rule (flow control) ------------------------------------------
    def _validate_state_rule(self, sr, params, control_ids, edit_ids):
        edits = sr.findall("Edit")
        if len(edits) != 1:
            self.error("SRULE-01", sr,
                       f"StateRule must contain exactly one Edit (found {len(edits)}).")
        self._check_bool(sr, "enabled", "SRULE-02")
        self._check_bool(sr, "visible", "SRULE-02")
        for edit in edits:
            self._validate_edit(edit, context="stateRule",
                                 params=params, control_ids=control_ids, edit_ids=edit_ids)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def validate_string(xml_text, source="<string>"):
    """Validate FIXatdl XML supplied as a string. Returns a result dict."""
    try:
        root, lines = parse_xml(xml_text)
    except ParseError as exc:
        return {
            "valid": False,
            "source": source,
            "summary": {"errors": 1, "warnings": 0, "rules": len(RULES)},
            "errors": [{
                "rule_id": "XML-01", "severity": "error", "element": None,
                "attribute": None, "line": exc.line,
                "message": f"XML is not well-formed: {exc.message}",
            }],
        }

    v = _Validator(lines)
    v.validate(root)
    errors = [f for f in v.findings if f["severity"] == "error"]
    warnings = [f for f in v.findings if f["severity"] == "warning"]
    # stable ordering: by line then rule id
    v.findings.sort(key=lambda f: (f["line"] or 0, f["rule_id"]))
    return {
        "valid": len(errors) == 0,
        "source": source,
        "summary": {
            "errors": len(errors),
            "warnings": len(warnings),
            "rules": len(RULES),
        },
        "errors": v.findings,
    }


def validate_file(path):
    """Validate a FIXatdl XML document on disk. Returns a result dict."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return validate_string(text, source=str(path))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main(argv):
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}

    if len(args) != 1:
        sys.stderr.write(
            "Usage: python fixatdl_validator.py <document.xml> "
            "[--pretty] [--warnings-as-errors] [--list-rules]\n")
        return 2

    if "--list-rules" in flags:
        print(json.dumps(RULES, indent=2))
        return 0

    result = validate_file(args[0])

    if "--warnings-as-errors" in flags and result["summary"]["warnings"]:
        result["valid"] = False

    indent = 2 if "--pretty" in flags else None
    print(json.dumps(result, indent=indent))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))