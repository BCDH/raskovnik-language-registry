<?xml version="1.0" encoding="UTF-8"?>
<schema xmlns="http://purl.oclc.org/dsdl/schematron" queryBinding="xslt">
  <title>Raskovnik effective language-registry constraints</title>
  <ns prefix="tei" uri="http://www.tei-c.org/ns/1.0"/>

  <pattern id="document-shape">
    <rule context="tei:TEI">
      <assert test="@type = 'lex-0'">The registry TEI must have type="lex-0".</assert>
      <assert test="count(tei:teiHeader/tei:profileDesc/tei:langUsage) = 1">The display tree must have exactly one langUsage root.</assert>
      <assert test="count(tei:teiHeader/tei:revisionDesc/tei:change[@type = 'registryVersion']) = 1">The TEI must embed exactly one registry version change.</assert>
      <assert test="normalize-space(tei:teiHeader/tei:revisionDesc/tei:change[@type = 'registryVersion']/@n) != ''">The embedded registry version must be nonempty.</assert>
      <assert test="count(tei:text/tei:body/tei:p[normalize-space(.) != '']) &gt;= 1">The registry must contain explanatory text/body prose.</assert>
      <assert test="not(.//tei:taxonomy | .//tei:category | .//tei:xenoData)">taxonomy, category, and xenoData are forbidden.</assert>
    </rule>
  </pattern>

  <pattern id="node-identity-and-shape">
    <rule context="tei:language | tei:languageGrp">
      <assert test="normalize-space(@ident) != ''">Every display node requires a canonical code.</assert>
      <assert test="not(@ident = preceding::tei:language/@ident or @ident = preceding::tei:languageGrp/@ident or @ident = following::tei:language/@ident or @ident = following::tei:languageGrp/@ident)">Canonical node codes must be globally unique.</assert>
      <assert test="@type = 'family' or @type = 'language' or @type = 'variety' or @type = 'historical-stage' or @type = 'reconstructed-language' or @type = 'collective'">Node kind is outside the controlled vocabulary.</assert>
      <assert test="not(@parent or @parentId)">Display parentage must use physical nesting, not custom attributes.</assert>
      <assert test="count(tei:ident[@type = 'BCP47']) = 1">Every node requires exactly one BCP47 ident child.</assert>
      <assert test="normalize-space(tei:ident[@type = 'BCP47']) = @ident">The BCP47 ident text must equal the node code.</assert>
      <assert test="tei:ident[@type = 'BCP47']/@xml:id = concat('lang-', @ident)">The BCP47 technical xml:id must preserve the canonical code.</assert>
      <assert test="not(starts-with(@ident, 'x-rask-') or contains(@ident, '-x-rask-'))">The parallel x-rask private namespace is forbidden.</assert>
      <assert test="not(tei:name[@type = 'languageName'][@role = 'languageReferenceName'][not(@xml:lang = 'sr' or @xml:lang = 'en' or @xml:lang = 'de')])">Preferred names use only Serbian, English, and German.</assert>
      <assert test="count(tei:name[@type = 'languageName'][@role = 'languageReferenceName'][@xml:lang = 'en']) = 1">Every node requires exactly one pinned English preferred name.</assert>
      <assert test="not(tei:note[@type = 'selectionStatus'][@subtype = 'selectable']) or (count(tei:name[@type = 'languageName'][@role = 'languageReferenceName']) = 3 and count(tei:name[@type = 'languageName'][@role = 'languageReferenceName'][@xml:lang = 'sr']) = 1 and count(tei:name[@type = 'languageName'][@role = 'languageReferenceName'][@xml:lang = 'de']) = 1)">Selectable nodes must have exactly one Serbian, English, and German preferred name.</assert>
      <assert test="not(tei:note[@type = 'selectionStatus'][@subtype = 'nonselectable']) or (count(tei:name[@type = 'languageName'][@role = 'languageReferenceName'][@xml:lang = 'sr']) &lt;= 1 and count(tei:name[@type = 'languageName'][@role = 'languageReferenceName'][@xml:lang = 'de']) &lt;= 1)">Nonselectable ancestors may omit Serbian or German preferred names.</assert>
      <assert test="count(tei:note[@type = 'selectionStatus'][@subtype = 'selectable' or @subtype = 'nonselectable']) = 1">Every node requires one controlled selection-status note.</assert>
      <assert test="count(tei:note[@type = 'classificationStatus'][@subtype = 'reviewed' or @subtype = 'tentative' or @subtype = 'disputed']) = 1">Every node requires one controlled classification-status note.</assert>
      <assert test="count(tei:note[@type = 'classificationNote'][@xml:lang = 'sr']) &lt;= 1 and count(tei:note[@type = 'classificationNote'][@xml:lang = 'en']) &lt;= 1 and count(tei:note[@type = 'classificationNote'][@xml:lang = 'de']) &lt;= 1">Classification notes may occur at most once per supported language.</assert>
      <assert test="not(tei:note[@type = 'classificationNote'][not(@xml:lang = 'sr' or @xml:lang = 'en' or @xml:lang = 'de')])">Classification notes use only supported languages.</assert>
      <assert test="not((@type = 'family' or @type = 'collective') and tei:settingDesc/tei:place/tei:location/tei:geo)">Semantic families and collectives cannot carry asserted points.</assert>
      <assert test="not(@ident = 'mk' and tei:ident[@type = 'Glottolog'] = 'mace1250') or tei:settingDesc/tei:place/tei:location/tei:geo[normalize-space(.) = '41.5957 21.7932']">Macedonian mace1250 must retain the pinned Glottolog point.</assert>
      <assert test="count(tei:ident[@type = 'Wikidata']) &lt;= 1">A node may have at most one exact Wikidata identifier.</assert>
      <assert test="not(tei:ident[@type = 'Wikidata']) or (starts-with(normalize-space(tei:ident[@type = 'Wikidata']), 'Q') and string-length(substring(normalize-space(tei:ident[@type = 'Wikidata']), 2)) &gt; 0 and substring(normalize-space(tei:ident[@type = 'Wikidata']), 2, 1) != '0' and translate(substring(normalize-space(tei:ident[@type = 'Wikidata']), 2), '0123456789', '') = '')">Wikidata identifiers must be semantic item QIDs in canonical Q123 form.</assert>
      <assert test="not(tei:ident[@type = 'Wikidata'] = preceding::tei:ident[@type = 'Wikidata'] or tei:ident[@type = 'Wikidata'] = following::tei:ident[@type = 'Wikidata'])">Exact Wikidata QIDs must be globally unique.</assert>
    </rule>
    <rule context="tei:language">
      <assert test="@role = 'objectLanguage'">Every terminal language must have role="objectLanguage".</assert>
    </rule>
    <rule context="tei:languageGrp">
      <assert test="not(@role)">languageGrp must not carry @role.</assert>
      <assert test="tei:language or tei:languageGrp">A languageGrp must exist only where the display node has children.</assert>
    </rule>
  </pattern>

  <pattern id="profile-and-source-record-contract">
    <rule context="tei:note">
      <assert test="not(@type = 'tagProfile' and @subtype = 'direct') or normalize-space(.) = ancestor::*[self::tei:language or self::tei:languageGrp][1]/@ident">A direct tag profile code must equal its containing node code.</assert>
      <assert test="not(@type = 'tagProfile' and @subtype = 'direct') or @xml:id = concat('profile-', normalize-space(.))">A tag-profile technical xml:id must preserve the canonical code.</assert>
    </rule>
    <rule context="tei:name">
      <assert test="not(@type = 'sourceLabel') or @role = 'language-label' or @role = 'compound-language-label'">Source-record kind is outside the controlled vocabulary.</assert>
      <assert test="not(@type = 'sourceLabel') or @subtype = 'abbreviation' or @subtype = 'label-only'">Source-label abbreviation state must be explicit.</assert>
      <assert test="not(@type = 'sourceLabel') or @xml:lang = 'sr'">The count-free conversion source label must be Serbian.</assert>
      <assert test="not(@type = 'sourceLabel') or normalize-space(@xml:id) != ''">Every source record requires a stable xml:id.</assert>
      <assert test="not(@type = 'sourceLabel') or count(../tei:note[@type = 'tagProfile'][@subtype = 'direct']) = 1">Every source record must belong to a node with exactly one direct tag profile.</assert>
      <assert test="not(@type = 'sourceLabel') or contains(concat(' ', normalize-space(@ana), ' '), ' #catalog-')">Every source record must explicitly identify one dictionary catalog.</assert>
      <assert test="not(@type = 'sourceLabel') or count(../tei:name[@type = 'sourceRecordLabel']) = 3 * count(../tei:name[@type = 'sourceLabel'])">Each source record requires exactly three localized labels.</assert>
    </rule>
  </pattern>

  <pattern id="provenance-and-alternate-lineages">
    <rule context="*">
      <assert test="not(@source) or starts-with(@source, '#')">Every source pointer must use a same-document xml:id reference.</assert>
    </rule>
    <rule context="tei:note">
      <assert test="not(@type = 'alternateClassification') or @subtype = 'reviewed' or @subtype = 'tentative' or @subtype = 'disputed'">Alternate-classification status is outside the controlled vocabulary.</assert>
      <assert test="not(@type = 'alternateClassification') or starts-with(@ana, '#')">Alternate classification IDs must use same-document xml:id references.</assert>
      <assert test="not(@type = 'alternateClassification') or tei:ref[@type = 'alternatePathNode']">Alternate classification requires a nonempty ordered path.</assert>
    </rule>
    <rule context="tei:ref">
      <assert test="not(@type = 'alternatePathNode') or starts-with(@target, '#lang-')">Alternate path targets must use canonical BCP47 technical identifiers.</assert>
    </rule>
  </pattern>

  <pattern id="locations">
    <rule context="tei:location">
      <assert test="@type = 'representative' or @type = 'historical' or @type = 'editorial'">Location type is outside the controlled vocabulary.</assert>
      <assert test="count(tei:geo) = 1">Each registry location must contain exactly one geo point.</assert>
      <assert test="normalize-space(../tei:idno[@type = 'sourceNode']) != ''">Each registry location must retain its source-node identifier.</assert>
    </rule>
    <rule context="tei:geo">
      <assert test="not(parent::tei:location) or (contains(normalize-space(.), ' ') and not(contains(substring-after(normalize-space(.), ' '), ' ')))">geo must contain exactly two whitespace-separated coordinates.</assert>
      <assert test="not(parent::tei:location) or (number(substring-before(normalize-space(.), ' ')) = number(substring-before(normalize-space(.), ' ')) and number(substring-before(normalize-space(.), ' ')) &gt;= -90 and number(substring-before(normalize-space(.), ' ')) &lt;= 90)">Latitude must be numeric and within WGS84 bounds.</assert>
      <assert test="not(parent::tei:location) or (number(substring-after(normalize-space(.), ' ')) = number(substring-after(normalize-space(.), ' ')) and number(substring-after(normalize-space(.), ' ')) &gt;= -180 and number(substring-after(normalize-space(.), ' ')) &lt;= 180)">Longitude must be numeric and within WGS84 bounds.</assert>
    </rule>
  </pattern>
</schema>
