xquery version "3.1";

import module namespace sm = "http://exist-db.org/xquery/securitymanager";
import module namespace xmldb = "http://exist-db.org/xquery/xmldb";

declare variable $target external;

declare %private variable $group-permissions as map(xs:string, xs:string)+ := (
    map { "name": "raskovnik-editors", "collection": "rwx", "resource": "rw-" },
    map { "name": "raskovnik-readers", "collection": "r-x", "resource": "r--" },
    map { "name": "raskovnik-executioners-public", "collection": "r-x", "resource": "r--" },
    map { "name": "raskovnik-executioners-private", "collection": "r-x", "resource": "r--" },
    map { "name": "raskovnik-executioners-admin", "collection": "r-x", "resource": "r--" },
    map { "name": "raskovnik-devs", "collection": "r-x", "resource": "r--" }
);

declare %private function local:ensure-group($group-name as xs:string) as empty-sequence() {
    if (sm:group-exists($group-name)) then
        ()
    else
        let $_ := sm:create-group($group-name)
        return ()
};

declare %private function local:remove-group-aces($path as xs:string, $group-name as xs:string) as empty-sequence() {
    let $indices :=
        reverse(
            sm:get-permissions(xs:anyURI($path))//*:ace[@target = "GROUP"][@who = $group-name]/@index
            ! xs:int(.)
        )
    let $_ :=
        for $index in $indices
        return sm:remove-ace(xs:anyURI($path), $index)
    return ()
};

declare %private function local:set-group-ace($path as xs:string, $group-name as xs:string, $permission as xs:string) as empty-sequence() {
    let $_ := local:remove-group-aces($path, $group-name)
    let $_ := sm:add-group-ace(xs:anyURI($path), $group-name, true(), $permission)
    return ()
};

declare %private function local:apply-recursively($collection as xs:string, $permissions as map(xs:string, xs:string)) as empty-sequence() {
    let $group-name := $permissions?name
    let $_ := local:set-group-ace($collection, $group-name, $permissions?collection)
    let $_ :=
        for $resource in xmldb:get-child-resources($collection)
        return local:set-group-ace($collection || "/" || $resource, $group-name, $permissions?resource)
    let $_ :=
        for $child in xmldb:get-child-collections($collection)
        return local:apply-recursively($collection || "/" || $child, $permissions)
    return ()
};

if (xmldb:collection-available($target)) then
    for $permissions in $group-permissions
    let $_ := local:ensure-group($permissions?name)
    return local:apply-recursively($target, $permissions)
else
    ()
