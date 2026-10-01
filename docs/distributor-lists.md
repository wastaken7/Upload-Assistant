# Distributor list comparison

Compared on 2026-10-01 against upstream [`DistributorSeeder.php`](https://github.com/HDInnovations/UNIT3D/blob/master/database/seeders/DistributorSeeder.php) (Git blob `140d111174b4c53093ee4a9def89f514cb10035f`) and the supplied tracker snapshots. Names are compared case-insensitively; accents, punctuation and spacing remain significant.

The default ID set contains only upstream IDs. Existing UA aliases are retained for upstream IDs, with canonical upstream names taking precedence. Tracker files contain only additions and canonical name/ID differences from the default. At runtime they are merged with the default; `excluded_ids` preserves upstream entries absent from each snapshot. Trackers without a snapshot use the upstream default.

The default JSON retains the upstream source URL. Tracker JSON files contain distributor differences and any excluded IDs; empty `distributors` objects without exclusions confirm a checked list matches upstream; retrieval dates and hashes are omitted from all lists. They are included in installed packages. Both uploads and metadata reads select the tracker’s mapping; reverse lookup returns its canonical name. Unsupported supplied names are preserved, optional distributor IDs are omitted, and ULCX is skipped when its mandatory distributor cannot be mapped.

## UA default versus upstream

Upstream defines 965 distributors (IDs 1–965). UA previously mapped 1718 names/aliases to 963 distinct IDs. No UA numeric IDs were outside the upstream set.

| Name | Previous UA ID | Upstream ID |
|---|---:|---:|
| CAPITOL | 159 | 158 |
| COLUMBIA | 203 | 202 |

Canonical names now take priority: CAPITOL is 158 (159 is Capitol Records), and COLUMBIA is 202 (203 is Columbia Pictures).

## Tracker snapshots versus upstream

| Tracker | Entries | Additional IDs | Missing upstream IDs | Renamed upstream IDs |
|---|---:|---:|---:|---:|
| AITHER | 1022 | 59 | 2 | 1 |
| ASIANCINEMA | 1011 | 48 | 2 | 1 |
| BLUTOPIA | 1351 | 387 | 1 | 1 |
| DARKPEERS | 965 | 0 | 0 | 0 |
| HAWKEUNO | 25 | 0 | 940 | 25 |
| ITATORRENTS | 968 | 3 | 0 | 0 |
| LATTEAM | 0 | 0 | 965 | 0 |
| OLDTOONSWORLD | 970 | 5 | 0 | 0 |
| ONLYENCODES | 967 | 2 | 0 | 0 |
| POLISHTORRENT | 1019 | 55 | 1 | 1 |
| RASTASTUGAN | 965 | 0 | 0 | 0 |
| REELFLIX | 966 | 1 | 0 | 0 |
| SHAREISLAND | 971 | 6 | 0 | 0 |
| THEOLDSCHOOL | 965 | 0 | 0 | 0 |
| ULCX | 973 | 8 | 0 | 0 |

HAWKEUNO uses its own distributor IDs. LATTEAM’s supplied dropdown contains only “Other”; its override excludes all upstream distributor IDs.

## AITHER

### Missing or renamed upstream entries

| ID | Upstream name | Tracker name |
|---:|---|---|
| 18 | A Contracorriente | Absent |
| 473 | Kinowelt Home Entertainment/DVD | Kinowelt Home Entertainment |
| 757 | Senator | Absent |

### Additional entries

| ID | Tracker name |
|---:|---|
| 966 | ABC Studios |
| 967 | Plaion |
| 968 | Crunchyroll, LLC |
| 969 | Cinématographe |
| 970 | Chameleon Films |
| 971 | Decal Releasing |
| 972 | Saturn's Core Audio & Video |
| 973 | Radiance Films |
| 974 | Warner Archive Collection |
| 975 | Terror Vision |
| 976 | Celluloid Dreams |
| 977 | Gabita Barbieri Films |
| 978 | Canadian International Pictures |
| 979 | Dark Star Pictures |
| 980 | Level 33 Entertainment |
| 981 | Arthaus |
| 982 | Factory25 |
| 983 | Indicator |
| 984 | Utopia Distribution |
| 985 | Janson Media |
| 986 | Lost Time Media |
| 987 | ADV Films |
| 988 | Bandai Entertainment |
| 989 | Melusine |
| 990 | Central Park Media |
| 991 | U.S. Manga Corps |
| 992 | Cult Media |
| 993 | Infinity Arthouse |
| 994 | A24 |
| 995 | PolyGram Video |
| 996 | VIZ Media, LLC |
| 997 | Genius Entertainment |
| 998 | Artisan Home Entertainment |
| 999 | The Film Preserve |
| 1000 | Lightbulb Film Distribution |
| 1001 | Indeed Film |
| 1002 | Old Gold Media |
| 1003 | Cine Plus Home Entertainment |
| 1004 | Patriot Films |
| 1005 | Terminal Video |
| 1006 | Sandpiper Pictures |
| 1007 | Ostalgica |
| 1008 | Distrimax |
| 1009 | Planet Media Home Entertainment |
| 1010 | Numax |
| 1011 | KimStim |
| 1012 | Pro-Fun Media |
| 1013 | Zorro Medien |
| 1014 | Wild Bunch Benelux |
| 1015 | Allumination FilmWorks |
| 1016 | New Line Home Video |
| 1017 | Cloud Ten Pictures |
| 1018 | Kinowelt Film Entertainment |
| 1019 | Visual Vengeance |
| 1020 | Senator Home Entertainment |
| 1021 | Toy Robot Video |
| 1022 | Modern Films |
| 1023 | POLAR Film |
| 1024 | Medien |

## ASIANCINEMA

### Missing or renamed upstream entries

| ID | Upstream name | Tracker name |
|---:|---|---|
| 17 | @Anime | Absent |
| 126 | Bill Zebub | Absent |
| 253 | Disney / Buena Vista | Disney |

### Additional entries

| ID | Tracker name |
|---:|---|
| 966 | ABC Studios |
| 967 | ADV Films |
| 968 | Arthaus |
| 969 | ArtsMagic |
| 970 | Bandai Entertainment |
| 971 | Canadian International Pictures |
| 972 | Celluloid Dreams |
| 973 | Central Park Media |
| 974 | Chameleon Films |
| 975 | Channel One |
| 976 | Chimera Entertainment |
| 977 | Cinématographe |
| 978 | Crunchyroll, LLC |
| 979 | Dark Star Pictures |
| 980 | Decal Releasing |
| 981 | Error 4444 |
| 982 | Factory25 |
| 983 | Gabita Barbieri Films |
| 984 | Indicator |
| 985 | Janson Media |
| 986 | Joy Sales |
| 987 | Level 33 Entertainment |
| 988 | Lost Time Media |
| 989 | Melusine |
| 990 | Panik House |
| 991 | Pioneer |
| 992 | Plaion |
| 993 | Radiance Films |
| 994 | Rentrak |
| 995 | SamuraiDVD |
| 996 | Saturn's Core Audio & Video |
| 997 | Terror Vision |
| 998 | U.S. Manga Corps |
| 999 | Urban Vision |
| 1000 | Utopia Distribution |
| 1001 | Warner Archive Collection |
| 1002 | Whole Grain Pictures |
| 1003 | Afilm |
| 1004 | Deaf Crocodile |
| 1005 | Pathfinder Home Entertainment |
| 1006 | Hong Kong Legends |
| 1007 | Scholar Video |
| 1008 | Buena Vista |
| 1010 | Kani Releasing |
| 1011 | Wonder Multimídia |
| 1012 | Anime Factory |
| 1013 | Xenon |
| 1014 | KSM Anime |

## BLUTOPIA

### Missing or renamed upstream entries

| ID | Upstream name | Tracker name |
|---:|---|---|
| 18 | A Contracorriente | Absent |
| 820 | Studio Canal | StudioCanal |

### Additional entries

| ID | Tracker name |
|---:|---|
| 966 | Plumeria Pictures |
| 967 | Indicator |
| 968 | Crocofilms |
| 969 | Plaion |
| 970 | Hallmark |
| 971 | Arcadès |
| 972 | Clavis Films |
| 973 | Decal Releasing |
| 974 | Mayfly |
| 975 | Radiance Films |
| 976 | IndiePix Films |
| 977 | ND Play |
| 978 | Cineriz |
| 979 | Cinematografica |
| 980 | Pierrot Le Fou |
| 981 | Giant Interactive |
| 982 | Showshank Films |
| 983 | TFC |
| 984 | A24 |
| 985 | Crunchyroll, LLC |
| 986 | Mediacs |
| 987 | Happy Entertainment |
| 988 | Error 4444 |
| 989 | Big World Pictures |
| 990 | Cinématographe |
| 991 | September Film |
| 992 | Cinehollywood |
| 993 | Re:Voir |
| 994 | Warren Miller Entertainment |
| 995 | Flashback Entertainment |
| 996 | Survivance |
| 997 | Teton Gravity Research |
| 998 | Sphere Films |
| 999 | Dauntless Studios |
| 1001 | Cartuna |
| 1002 | Program Store |
| 1003 | Ryko Distribution |
| 1004 | Bleeding Skull |
| 1005 | Midnight Factory |
| 1006 | ABC - (American Broadcasting Corporation) |
| 1007 | Hammer Films |
| 1008 | Indeed Film |
| 1009 | SND |
| 1010 | Vintage Classics |
| 1011 | Ostalgica |
| 1012 | Dark Star Pictures |
| 1013 | OneGate Media |
| 1014 | Distribpix |
| 1015 | Level 33 Entertainment |
| 1016 | Shoreline Entertainment |
| 1017 | WMM |
| 1018 | Source 1 Media B.V. |
| 1019 | Criterion Collection - Criterion Premieres |
| 1020 | ETR Media |
| 1021 | Yellow Veil Pictures |
| 1022 | Alpha Video |
| 1023 | Terror Vision |
| 1024 | Black Bear |
| 1025 | Factory25 |
| 1026 | Memory |
| 1027 | Utopia Distribution |
| 1028 | Indies Entertainment |
| 1029 | Interesting Films Different Perspectives |
| 1030 | Arcade Video |
| 1031 | Passport Video |
| 1032 | Contender Entertainment Group |
| 1033 | Elokuvapalvelu J. Suomalainen |
| 1034 | Isla Sales |
| 1035 | Mis Label |
| 1036 | Jupiter |
| 1037 | AtlanticFilm |
| 1038 | Molot Entertainment |
| 1039 | LumimiesFilmi |
| 1040 | Finnkino |
| 1041 | International Sami Film Institute |
| 1042 | Aamu Film Company |
| 1043 | Artista Filmi |
| 1044 | Edito Films |
| 1045 | EPF Media |
| 1046 | Immina Films |
| 1047 | Kumar Films |
| 1048 | Tartan Video |
| 1049 | Seven Springs Pictures |
| 1050 | Icarus Films |
| 1051 | Blue Water Content |
| 1052 | FilmNation Entertainment |
| 1053 | Videodis |
| 1054 | Catcom Home Video |
| 1055 | Cinephobia Releasing |
| 1056 | Group Gendai Films |
| 1057 | Bounty Films |
| 1058 | Folkets Bio |
| 1059 | Tanelorn Films |
| 1060 | Zillion Film |
| 1061 | Thai Film Archive |
| 1062 | Musictronic Entertainment |
| 1063 | ITV Studios Home Entertainment |
| 1064 | Home Vision Entertainment |
| 1065 | 2Good |
| 1066 | Allied Vaughn |
| 1067 | Attraction distribution |
| 1068 | AUD |
| 1069 | Bayview |
| 1070 | Bel Canto |
| 1071 | Bim |
| 1072 | Bluebell Films |
| 1073 | Brentwood |
| 1074 | Bretz Filmes |
| 1075 | British Home Entertainment |
| 1076 | Cahiers du cinéma |
| 1077 | CDI |
| 1078 | Centre Audiovisuel Simone de Beauvoir |
| 1079 | CG Entertainment |
| 1080 | Channel 4 |
| 1081 | Christal Films |
| 1082 | Chrystal Films |
| 1083 | Cinelicious Pics |
| 1084 | CMF |
| 1085 | Command Video |
| 1086 | Corinth Films |
| 1087 | Cristaldi Film |
| 1088 | D & D Glass and Wyatt |
| 1089 | Daiei |
| 1090 | Dark Sky Films |
| 1091 | David Burton Morris Films |
| 1092 | Deaf Crocodile |
| 1093 | Degausser Video |
| 1094 | Dekanalog |
| 1095 | Docurama |
| 1096 | Dreamscape |
| 1097 | Ediciones 79 |
| 1098 | Eesti Film 100 |
| 1099 | Elite Entertainment |
| 1100 | Epicentre Films |
| 1101 | Eureka - Masters of Cinema |
| 1102 | Euston Home Entertainment |
| 1103 | Fantoma |
| 1104 | FILM 2000 |
| 1105 | Film Preservation Society |
| 1106 | FilmBuff |
| 1107 | Filmgalerie 451 |
| 1108 | Filmhub |
| 1109 | Filmotronik |
| 1110 | First Run Features |
| 1111 | Frameline |
| 1112 | Futurama |
| 1113 | Genius Entertainment |
| 1114 | Globo Filmes |
| 1115 | Goldhil Video |
| 1116 | Good Guys Media |
| 1117 | GZbeauty |
| 1118 | Hart Sharp |
| 1119 | Hip-o Records |
| 1120 | Infinity Arthouse |
| 1121 | Infinity Entertainment |
| 1122 | Janus Films |
| 1123 | Joy Sales |
| 1124 | Kiddiepunk |
| 1125 | KimStim |
| 1126 | Korean Film Archive |
| 1127 | Krupnyy Plan |
| 1128 | La Entertainment |
| 1129 | La Rabbia |
| 1130 | La Traverse |
| 1131 | La Vie est Belle |
| 1132 | Lava |
| 1133 | Les documents cinématographiques |
| 1134 | Les films de ma vie |
| 1135 | Les Films du 3 Mars |
| 1136 | Les films du Camélia |
| 1137 | Liberation Hall |
| 1138 | Lightbulb Film Distribution |
| 1139 | Lusomundo |
| 1140 | Madacy Entertainment |
| 1141 | Maison4tiers |
| 1142 | Malavida |
| 1143 | Mawu Films |
| 1144 | McIntyre Media Inc |
| 1145 | MHZ |
| 1146 | Mikado |
| 1147 | NBC Home Video |
| 1148 | New Video |
| 1149 | NGi |
| 1150 | NMC United Entertainment |
| 1151 | No Shame Films |
| 1152 | Oblivion |
| 1153 | Odyssey |
| 1154 | Odyssey Quest |
| 1155 | On Air |
| 1156 | Optimale |
| 1157 | Outcast Films |
| 1158 | Pathfinder Home Entertainment |
| 1159 | Payless Entertainment Limited |
| 1160 | Pioneer |
| 1161 | Planet DVD |
| 1162 | Platinum Disc |
| 1163 | Polygram |
| 1164 | Precision Pictures |
| 1165 | Rai − Radiotelevisione italiana |
| 1166 | Red Bull Media House |
| 1167 | Reelin' in the Years |
| 1168 | Renown |
| 1169 | René Chateau Video |
| 1170 | Republic Pictures |
| 1171 | Ruscico |
| 1172 | Rustblade |
| 1173 | Salzgeber & Co. |
| 1174 | Sanctuary Records |
| 1175 | Shellac |
| 1176 | Simply Media |
| 1177 | Slam Dunk Media |
| 1178 | Smore Entertainment |
| 1179 | Sogepaq |
| 1180 | Something Weird |
| 1181 | Sprocket Vault |
| 1182 | Stone Lantern Films |
| 1183 | Strawberry Media |
| 1184 | Studio Canal |
| 1185 | Sub Rosa |
| 1186 | Sullivan Entertainment |
| 1187 | Sundance |
| 1188 | Surf Video |
| 1189 | Tango Entertainment |
| 1190 | Televista |
| 1191 | TGG Direct |
| 1192 | THANK U INTERNATIONAL CO., LTD. |
| 1193 | The Film Desk |
| 1194 | The Film Preserve |
| 1195 | The Third Ear |
| 1196 | Treasured Films |
| 1197 | Tribeca |
| 1198 | UFO Distribution |
| 1199 | VAI |
| 1200 | Vanguard |
| 1201 | Vidangel Studios |
| 1202 | Video Project |
| 1203 | View Video |
| 1204 | Warner Archive Collection |
| 1205 | Water Bearer Films |
| 1206 | Wellspring |
| 1207 | White Pine Pictures |
| 1208 | Wild East |
| 1209 | Yume Pictures |
| 1210 | Anti-Worlds |
| 1211 | Ariztical Entertainment |
| 1212 | Artisan |
| 1213 | Asian Film Archive |
| 1214 | Atalanta Filmes |
| 1215 | Athena |
| 1216 | B-Spree Classics |
| 1217 | Canadian International Pictures |
| 1218 | Cardinal Releasing |
| 1219 | Carlton |
| 1220 | Chameleon Films |
| 1221 | Cinecom |
| 1222 | Cinema Club |
| 1223 | Cinemagi |
| 1224 | Colored Films |
| 1225 | Crash Cinema |
| 1226 | DD Home Entertainment |
| 1227 | Digital Classics |
| 1228 | Digital Element |
| 1229 | Digital Meme |
| 1230 | Distrib Films |
| 1231 | Edition Filmmuseum |
| 1232 | Element Pictures |
| 1233 | Encore |
| 1234 | Facets |
| 1235 | Film Foetus |
| 1236 | Film Masters |
| 1237 | Films Sans Frontieres |
| 1238 | Fractured Visions |
| 1239 | Framehammer Films |
| 1240 | Global Film |
| 1241 | Globus Group |
| 1242 | Good Times |
| 1243 | HD Cinema Classics |
| 1244 | Home Movies |
| 1245 | Ignite Films |
| 1246 | Illuminations |
| 1247 | Level 1 Productions |
| 1248 | Liberation Entertainment |
| 1249 | Mediabook |
| 1250 | Millennium Storm |
| 1251 | Mondo Home Entertainment (Italy) |
| 1252 | More Entertainment |
| 1253 | Neon |
| 1254 | New Star |
| 1255 | New Yorker Films |
| 1256 | Nikkatsu |
| 1257 | Novy Disk |
| 1258 | Palm Pictures |
| 1259 | Panik House |
| 1260 | Picture This |
| 1261 | Plan B |
| 1262 | Plexifilm |
| 1263 | Reel Rock |
| 1264 | RHI |
| 1265 | Rykodisc |
| 1266 | Sandpiper Pictures |
| 1267 | Screen Archives Entertainment |
| 1268 | Shanachie |
| 1269 | Sogemedia |
| 1270 | Sovereign Film |
| 1271 | Studio 24 |
| 1272 | Subversive Cinema |
| 1273 | Taiwan Film Institute |
| 1274 | ThinkFilm |
| 1275 | Trimark |
| 1276 | Typecast Releasing |
| 1277 | Undercrank Productions |
| 1278 | VIPCO |
| 1279 | Vision Film (Poland) |
| 1280 | Winstar |
| 1281 | Xenon |
| 1282 | 1091 |
| 1283 | Gemini Vidéo Editions |
| 1284 | Hollywood DVD |
| 1285 | Impulse Pictures |
| 1286 | Impulso |
| 1287 | Kani |
| 1288 | Lance Entertainment |
| 1289 | Mya |
| 1290 | Studio Distribution Services |
| 1291 | Hardy Classic Video |
| 1292 | Optimum World |
| 1293 | Rabinovich Foundation |
| 1294 | Nu Boyana |
| 1295 | Israeli Film Fund |
| 1296 | Arthaus |
| 1297 | Microcinema |
| 1298 | Doriane Films |
| 1299 | ScanTrade |
| 1300 | Feel Films |
| 1301 | Manga Films |
| 1302 | Buena Vista |
| 1303 | Retro Gold 63 |
| 1304 | Domino Film |
| 1305 | Transformer |
| 1306 | ADV Films |
| 1307 | Bandai Entertainment |
| 1308 | Les Films du Paradoxe |
| 1309 | Mundo en DVD |
| 1310 | Central Park Media |
| 1311 | Manga Corps |
| 1312 | Sabotakt |
| 1313 | Monarch Home Entertainment |
| 1314 | Lookout Mountain Studio |
| 1315 | Eastwind Films |
| 1316 | CNN |
| 1317 | Strada Film |
| 1318 | Epelpol |
| 1319 | National Film Board of Canada |
| 1320 | MarFilmes |
| 1321 | ICA |
| 1322 | Illume |
| 1323 | Istituto Luce |
| 1324 | Vinca Film |
| 1325 | Make Peace Productons |
| 1326 | Olydri |
| 1327 | Fox Lorber |
| 1328 | Flashstar Home Entertainment |
| 1329 | Burning Bulb Productions |
| 1330 | DVD Pocket |
| 1331 | Slovenian Film Centre |
| 1332 | Imagine Film Distribution |
| 1333 | Filmoteca Española |
| 1334 | ReFresh |
| 1335 | Acme Film |
| 1336 | P.O.M. Films |
| 1337 | Cattleya |
| 1338 | Vértice Cine |
| 1339 | Mokép |
| 1340 | Fandango |
| 1341 | AVH |
| 1342 | Gabita Barbieri Films |
| 1343 | Night Visions |
| 1344 | Embrem Entertainment |
| 1345 | Modern Films |
| 1346 | Norma Productions |
| 1347 | United King Films |
| 1348 | Vision Video UK |
| 1349 | KinoVista |
| 1350 | Route One Releasing |
| 1351 | Tabu |
| 1352 | Periscope Film |
| 1353 | Anderson Merchandise |

## DARKPEERS

### Missing or renamed upstream entries

No missing or renamed upstream entries.

## HAWKEUNO

HAWKEUNO uses IDs 1–25 for its own list. All upstream IDs 26–965 are absent; their explicit exclusions are recorded in `data/distributors/hawkeuno.json`.

### Remapped upstream IDs

| ID | Upstream name | Tracker name |
|---:|---|---|
| 1 | 01 Distribution | Criterion Collection |
| 2 | 100 Destinations Travel Film | British Film Institute |
| 3 | 101 Films | Arrow Video |
| 4 | 1Films | Shout Factory |
| 5 | 2 Entertain Video | Indicator |
| 6 | 20th Century Fox | Eureka Entertainment |
| 7 | 2L | Kino Lorber |
| 8 | 3D Content Hub | Second Sight Films |
| 9 | 3D Media | Twilight Time |
| 10 | 3L Film | Vinegar Syndrome |
| 11 | 4Digital | 88 Films |
| 12 | 4dvd | Imprint |
| 13 | 4K Ultra HD Movies | Umbrella Entertainment |
| 14 | 8-Films | Severin Films |
| 15 | 84 Entertainment | Blue Underground |
| 16 | 88 Films | Synapse Films |
| 17 | @Anime | Scream Factory |
| 18 | A Contracorriente | Mill Creek Entertainment |
| 19 | A Contracorriente Films | Warner Archive |
| 20 | A&E Home Video | Sony Pictures Classics |
| 21 | A&M Records | Universal Pictures |
| 22 | A+E Networks | Paramount Pictures |
| 23 | A+R | Disney |
| 24 | A-film | Lionsgate |
| 25 | AAA | A24 |

## ITATORRENTS

### Missing or renamed upstream entries

No missing or renamed upstream entries.

### Additional entries

| ID | Tracker name |
|---:|---|
| 966 | Altro |
| 967 | Universal Pictures |
| 968 | Prime Video |

## LATTEAM

### Missing or renamed upstream entries

All upstream IDs (1–965) are absent.

## OLDTOONSWORLD

### Missing or renamed upstream entries

No missing or renamed upstream entries.

### Additional entries

| ID | Tracker name |
|---:|---|
| 966 | Deaf Crocodile |
| 967 | Rhino Home Video |
| 968 | US Manga Corps |
| 969 | ADV Films |
| 970 | Crunchyroll |

## ONLYENCODES

### Missing or renamed upstream entries

No missing or renamed upstream entries.

### Additional entries

| ID | Tracker name |
|---:|---|
| 966 | Level 33 Entertainment |
| 967 | A24 |

## POLISHTORRENT

### Missing or renamed upstream entries

| ID | Upstream name | Tracker name |
|---:|---|---|
| 17 | @Anime | Absent |
| 253 | Disney / Buena Vista | Disney + |

### Additional entries

| ID | Tracker name |
|---:|---|
| 966 | PTTRiP |
| 967 | Kadr |
| 968 | Walt Disney Production |
| 969 | Prime ➡️ |
| 970 | Studio Filmowe Perspektywa |
| 971 | Telewizja Polska |
| 972 | Canal+ Polska |
| 973 | Dimension Films |
| 974 | Hanna-Barbera |
| 975 | Cinerama |
| 976 | Universla release |
| 977 | Dino De Laurentiis |
| 978 | A24 |
| 979 | Player |
| 980 | TVN |
| 981 | Prime Video |
| 982 | MAX |
| 983 | Viaplay |
| 984 | Amazon Prime |
| 985 | TVP VOD |
| 986 | TVP Sport |
| 987 | WP Pilot |
| 988 | Megogo |
| 989 | Extreme+ |
| 990 | Polsat Box Go |
| 991 | HBO MAX |
| 992 | Canal+ Online |
| 993 | Play Now |
| 994 | Televio |
| 995 | Skyshowtime |
| 996 | Apple TV+ |
| 997 | CDA Premium |
| 998 | Rakuten |
| 999 | iTunes |
| 1000 | Ninateka |
| 1001 | E-Kino Pod Baranami |
| 1002 | MOJEeKINO |
| 1003 | Nowe Horyzonty |
| 1004 | Pięć Smaków |
| 1005 | VOD.MDAG.PL |
| 1006 | Katoflix |
| 1007 | Outfilm |
| 1008 | 35mm.online |
| 1009 | FlixClassic |
| 1010 | VOD Warszawa |
| 1011 | CHILI |
| 1012 | RED GO |
| 1013 | ARTE po polsku |
| 1014 | TVSmart |
| 1015 | FAME MMA |
| 1016 | CLOUT MMA |
| 1017 | PRIME MMA |
| 1018 | KSW |
| 1019 | IPLA VOD |
| 1020 | Kino Polska TV |

## RASTASTUGAN

### Missing or renamed upstream entries

No missing or renamed upstream entries.

## REELFLIX

### Missing or renamed upstream entries

No missing or renamed upstream entries.

### Additional entries

| ID | Tracker name |
|---:|---|
| 966 | Radiance Films |

## SHAREISLAND

### Missing or renamed upstream entries

No missing or renamed upstream entries.

### Additional entries

| ID | Tracker name |
|---:|---|
| 966 | Fandango |
| 967 | Universal Pictures Home Entertainment |
| 968 | Warner Home Video |
| 969 | Cecchi Gori Home Video |
| 970 | Terminal Video |
| 971 | CG Entertainment |

## THEOLDSCHOOL

### Missing or renamed upstream entries

No missing or renamed upstream entries.

## ULCX

### Missing or renamed upstream entries

No missing or renamed upstream entries.

### Additional entries

| ID | Tracker name |
|---:|---|
| 966 | Crunchyroll, LLC |
| 967 | Plaion Pictures |
| 968 | I Wonder Pictures |
| 969 | CG Entertainment |
| 970 | A24 |
| 971 | Radiance Films |
| 972 | ADV Films |
| 973 | Old Gold Media |

## Same name, different tracker IDs

| Distributor | AITHER | ASIANCINEMA | BLUTOPIA | DARKPEERS | HAWKEUNO | ITATORRENTS | LATTEAM | OLDTOONSWORLD | ONLYENCODES | POLISHTORRENT | RASTASTUGAN | REELFLIX | SHAREISLAND | THEOLDSCHOOL | ULCX |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 88 FILMS | 16 | 16 | 16 | 16 | 11 | 16 | — | 16 | 16 | 16 | 16 | 16 | 16 | 16 | 16 |
| A24 | 994 | — | 984 | — | 25 | — | — | — | 967 | 978 | — | — | — | — | 970 |
| ADV FILMS | 987 | 967 | 1306 | — | — | — | — | 969 | — | — | — | — | — | — | 972 |
| ARTHAUS | 981 | 968 | 1296 | — | — | — | — | — | — | — | — | — | — | — | — |
| BANDAI ENTERTAINMENT | 988 | 970 | 1307 | — | — | — | — | — | — | — | — | — | — | — | — |
| BLUE UNDERGROUND | 139 | 139 | 139 | 139 | 15 | 139 | — | 139 | 139 | 139 | 139 | 139 | 139 | 139 | 139 |
| BUENA VISTA | — | 1008 | 1302 | — | — | — | — | — | — | — | — | — | — | — | — |
| CANADIAN INTERNATIONAL PICTURES | 978 | 971 | 1217 | — | — | — | — | — | — | — | — | — | — | — | — |
| CELLULOID DREAMS | 976 | 972 | — | — | — | — | — | — | — | — | — | — | — | — | — |
| CENTRAL PARK MEDIA | 990 | 973 | 1310 | — | — | — | — | — | — | — | — | — | — | — | — |
| CG ENTERTAINMENT | — | — | 1079 | — | — | — | — | — | — | — | — | — | 971 | — | 969 |
| CHAMELEON FILMS | 970 | 974 | 1220 | — | — | — | — | — | — | — | — | — | — | — | — |
| CINÉMATOGRAPHE | 969 | 977 | 990 | — | — | — | — | — | — | — | — | — | — | — | — |
| CRUNCHYROLL, LLC | 968 | 978 | 985 | — | — | — | — | — | — | — | — | — | — | — | 966 |
| DARK STAR PICTURES | 979 | 979 | 1012 | — | — | — | — | — | — | — | — | — | — | — | — |
| DEAF CROCODILE | — | 1004 | 1092 | — | — | — | — | 966 | — | — | — | — | — | — | — |
| DECAL RELEASING | 971 | 980 | 973 | — | — | — | — | — | — | — | — | — | — | — | — |
| DISNEY | — | 253 | — | — | 23 | — | — | — | — | — | — | — | — | — | — |
| ERROR 4444 | — | 981 | 988 | — | — | — | — | — | — | — | — | — | — | — | — |
| EUREKA ENTERTAINMENT | 313 | 313 | 313 | 313 | 6 | 313 | — | 313 | 313 | 313 | 313 | 313 | 313 | 313 | 313 |
| FACTORY25 | 982 | 982 | 1025 | — | — | — | — | — | — | — | — | — | — | — | — |
| FANDANGO | — | — | 1340 | — | — | — | — | — | — | — | — | — | 966 | — | — |
| GABITA BARBIERI FILMS | 977 | 983 | 1342 | — | — | — | — | — | — | — | — | — | — | — | — |
| GENIUS ENTERTAINMENT | 997 | — | 1113 | — | — | — | — | — | — | — | — | — | — | — | — |
| IMPRINT | 430 | 430 | 430 | 430 | 12 | 430 | — | 430 | 430 | 430 | 430 | 430 | 430 | 430 | 430 |
| INDEED FILM | 1001 | — | 1008 | — | — | — | — | — | — | — | — | — | — | — | — |
| INDICATOR | 983 | 984 | 967 | — | 5 | — | — | — | — | — | — | — | — | — | — |
| INFINITY ARTHOUSE | 993 | — | 1120 | — | — | — | — | — | — | — | — | — | — | — | — |
| JOY SALES | — | 986 | 1123 | — | — | — | — | — | — | — | — | — | — | — | — |
| KIMSTIM | 1011 | — | 1125 | — | — | — | — | — | — | — | — | — | — | — | — |
| KINO LORBER | 470 | 470 | 470 | 470 | 7 | 470 | — | 470 | 470 | 470 | 470 | 470 | 470 | 470 | 470 |
| LEVEL 33 ENTERTAINMENT | 980 | 987 | 1015 | — | — | — | — | — | 966 | — | — | — | — | — | — |
| LIGHTBULB FILM DISTRIBUTION | 1000 | — | 1138 | — | — | — | — | — | — | — | — | — | — | — | — |
| LOST TIME MEDIA | 986 | 988 | — | — | — | — | — | — | — | — | — | — | — | — | — |
| MILL CREEK ENTERTAINMENT | 560 | 560 | 560 | 560 | 18 | 560 | — | 560 | 560 | 560 | 560 | 560 | 560 | 560 | 560 |
| MODERN FILMS | 1022 | — | 1345 | — | — | — | — | — | — | — | — | — | — | — | — |
| OLD GOLD MEDIA | 1002 | — | — | — | — | — | — | — | — | — | — | — | — | — | 973 |
| OSTALGICA | 1007 | — | 1011 | — | — | — | — | — | — | — | — | — | — | — | — |
| PANIK HOUSE | — | 990 | 1259 | — | — | — | — | — | — | — | — | — | — | — | — |
| PARAMOUNT PICTURES | 659 | 659 | 659 | 659 | 22 | 659 | — | 659 | 659 | 659 | 659 | 659 | 659 | 659 | 659 |
| PATHFINDER HOME ENTERTAINMENT | — | 1005 | 1158 | — | — | — | — | — | — | — | — | — | — | — | — |
| PIONEER | — | 991 | 1160 | — | — | — | — | — | — | — | — | — | — | — | — |
| PLAION | 967 | 992 | 969 | — | — | — | — | — | — | — | — | — | — | — | — |
| PRIME VIDEO | — | — | — | — | — | 968 | — | — | — | 981 | — | — | — | — | — |
| RADIANCE FILMS | 973 | 993 | 975 | — | — | — | — | — | — | — | — | 966 | — | — | 971 |
| SANDPIPER PICTURES | 1006 | — | 1266 | — | — | — | — | — | — | — | — | — | — | — | — |
| SATURN'S CORE AUDIO & VIDEO | 972 | 996 | — | — | — | — | — | — | — | — | — | — | — | — | — |
| SEVERIN FILMS | 760 | 760 | 760 | 760 | 14 | 760 | — | 760 | 760 | 760 | 760 | 760 | 760 | 760 | 760 |
| SHOUT FACTORY | 772 | 772 | 772 | 772 | 4 | 772 | — | 772 | 772 | 772 | 772 | 772 | 772 | 772 | 772 |
| SONY PICTURES CLASSICS | 795 | 795 | 795 | 795 | 20 | 795 | — | 795 | 795 | 795 | 795 | 795 | 795 | 795 | 795 |
| STUDIO CANAL | 820 | 820 | 1184 | 820 | — | 820 | — | 820 | 820 | 820 | 820 | 820 | 820 | 820 | 820 |
| SYNAPSE FILMS | 831 | 831 | 831 | 831 | 16 | 831 | — | 831 | 831 | 831 | 831 | 831 | 831 | 831 | 831 |
| TERMINAL VIDEO | 1005 | — | — | — | — | — | — | — | — | — | — | — | 970 | — | — |
| TERROR VISION | 975 | 997 | 1023 | — | — | — | — | — | — | — | — | — | — | — | — |
| THE FILM PRESERVE | 999 | — | 1194 | — | — | — | — | — | — | — | — | — | — | — | — |
| TWILIGHT TIME | 879 | 879 | 879 | 879 | 9 | 879 | — | 879 | 879 | 879 | 879 | 879 | 879 | 879 | 879 |
| U.S. MANGA CORPS | 991 | 998 | — | — | — | — | — | — | — | — | — | — | — | — | — |
| UMBRELLA ENTERTAINMENT | 888 | 888 | 888 | 888 | 13 | 888 | — | 888 | 888 | 888 | 888 | 888 | 888 | 888 | 888 |
| UNIVERSAL PICTURES | — | — | — | — | 21 | 967 | — | — | — | — | — | — | — | — | — |
| UTOPIA DISTRIBUTION | 984 | 1000 | 1027 | — | — | — | — | — | — | — | — | — | — | — | — |
| VINEGAR SYNDROME | 922 | 922 | 922 | 922 | 10 | 922 | — | 922 | 922 | 922 | 922 | 922 | 922 | 922 | 922 |
| WARNER ARCHIVE COLLECTION | 974 | 1001 | 1204 | — | — | — | — | — | — | — | — | — | — | — | — |
| XENON | — | 1013 | 1281 | — | — | — | — | — | — | — | — | — | — | — | — |

63 names have different IDs across the supplied trackers.

## Same ID, different tracker names

| ID | AITHER | ASIANCINEMA | BLUTOPIA | DARKPEERS | HAWKEUNO | ITATORRENTS | LATTEAM | OLDTOONSWORLD | ONLYENCODES | POLISHTORRENT | RASTASTUGAN | REELFLIX | SHAREISLAND | THEOLDSCHOOL | ULCX |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 01 Distribution | 01 Distribution | 01 Distribution | 01 Distribution | Criterion Collection | 01 Distribution | — | 01 Distribution | 01 Distribution | 01 Distribution | 01 Distribution | 01 Distribution | 01 Distribution | 01 Distribution | 01 Distribution |
| 2 | 100 Destinations Travel Film | 100 Destinations Travel Film | 100 Destinations Travel Film | 100 Destinations Travel Film | British Film Institute | 100 Destinations Travel Film | — | 100 Destinations Travel Film | 100 Destinations Travel Film | 100 Destinations Travel Film | 100 Destinations Travel Film | 100 Destinations Travel Film | 100 Destinations Travel Film | 100 Destinations Travel Film | 100 Destinations Travel Film |
| 3 | 101 Films | 101 Films | 101 Films | 101 Films | Arrow Video | 101 Films | — | 101 Films | 101 Films | 101 Films | 101 Films | 101 Films | 101 Films | 101 Films | 101 Films |
| 4 | 1Films | 1Films | 1Films | 1Films | Shout Factory | 1Films | — | 1Films | 1Films | 1Films | 1Films | 1Films | 1Films | 1Films | 1Films |
| 5 | 2 Entertain Video | 2 Entertain Video | 2 Entertain Video | 2 Entertain Video | Indicator | 2 Entertain Video | — | 2 Entertain Video | 2 Entertain Video | 2 Entertain Video | 2 Entertain Video | 2 Entertain Video | 2 Entertain Video | 2 Entertain Video | 2 Entertain Video |
| 6 | 20th Century Fox | 20th Century Fox | 20th Century Fox | 20th Century Fox | Eureka Entertainment | 20th Century Fox | — | 20th Century Fox | 20th Century Fox | 20th Century Fox | 20th Century Fox | 20th Century Fox | 20th Century Fox | 20th Century Fox | 20th Century Fox |
| 7 | 2L | 2L | 2L | 2L | Kino Lorber | 2L | — | 2L | 2L | 2L | 2L | 2L | 2L | 2L | 2L |
| 8 | 3D Content Hub | 3D Content Hub | 3D Content Hub | 3D Content Hub | Second Sight Films | 3D Content Hub | — | 3D Content Hub | 3D Content Hub | 3D Content Hub | 3D Content Hub | 3D Content Hub | 3D Content Hub | 3D Content Hub | 3D Content Hub |
| 9 | 3D Media | 3D Media | 3D Media | 3D Media | Twilight Time | 3D Media | — | 3D Media | 3D Media | 3D Media | 3D Media | 3D Media | 3D Media | 3D Media | 3D Media |
| 10 | 3L Film | 3L Film | 3L Film | 3L Film | Vinegar Syndrome | 3L Film | — | 3L Film | 3L Film | 3L Film | 3L Film | 3L Film | 3L Film | 3L Film | 3L Film |
| 11 | 4Digital | 4Digital | 4Digital | 4Digital | 88 Films | 4Digital | — | 4Digital | 4Digital | 4Digital | 4Digital | 4Digital | 4Digital | 4Digital | 4Digital |
| 12 | 4dvd | 4dvd | 4dvd | 4dvd | Imprint | 4dvd | — | 4dvd | 4dvd | 4dvd | 4dvd | 4dvd | 4dvd | 4dvd | 4dvd |
| 13 | 4K Ultra HD Movies | 4K Ultra HD Movies | 4K Ultra HD Movies | 4K Ultra HD Movies | Umbrella Entertainment | 4K Ultra HD Movies | — | 4K Ultra HD Movies | 4K Ultra HD Movies | 4K Ultra HD Movies | 4K Ultra HD Movies | 4K Ultra HD Movies | 4K Ultra HD Movies | 4K Ultra HD Movies | 4K Ultra HD Movies |
| 14 | 8-Films | 8-Films | 8-Films | 8-Films | Severin Films | 8-Films | — | 8-Films | 8-Films | 8-Films | 8-Films | 8-Films | 8-Films | 8-Films | 8-Films |
| 15 | 84 Entertainment | 84 Entertainment | 84 Entertainment | 84 Entertainment | Blue Underground | 84 Entertainment | — | 84 Entertainment | 84 Entertainment | 84 Entertainment | 84 Entertainment | 84 Entertainment | 84 Entertainment | 84 Entertainment | 84 Entertainment |
| 16 | 88 Films | 88 Films | 88 Films | 88 Films | Synapse Films | 88 Films | — | 88 Films | 88 Films | 88 Films | 88 Films | 88 Films | 88 Films | 88 Films | 88 Films |
| 17 | @Anime | — | @Anime | @Anime | Scream Factory | @Anime | — | @Anime | @Anime | — | @Anime | @Anime | @Anime | @Anime | @Anime |
| 18 | — | A Contracorriente | — | A Contracorriente | Mill Creek Entertainment | A Contracorriente | — | A Contracorriente | A Contracorriente | A Contracorriente | A Contracorriente | A Contracorriente | A Contracorriente | A Contracorriente | A Contracorriente |
| 19 | A Contracorriente Films | A Contracorriente Films | A Contracorriente Films | A Contracorriente Films | Warner Archive | A Contracorriente Films | — | A Contracorriente Films | A Contracorriente Films | A Contracorriente Films | A Contracorriente Films | A Contracorriente Films | A Contracorriente Films | A Contracorriente Films | A Contracorriente Films |
| 20 | A&E Home Video | A&E Home Video | A&E Home Video | A&E Home Video | Sony Pictures Classics | A&E Home Video | — | A&E Home Video | A&E Home Video | A&E Home Video | A&E Home Video | A&E Home Video | A&E Home Video | A&E Home Video | A&E Home Video |
| 21 | A&M Records | A&M Records | A&M Records | A&M Records | Universal Pictures | A&M Records | — | A&M Records | A&M Records | A&M Records | A&M Records | A&M Records | A&M Records | A&M Records | A&M Records |
| 22 | A+E Networks | A+E Networks | A+E Networks | A+E Networks | Paramount Pictures | A+E Networks | — | A+E Networks | A+E Networks | A+E Networks | A+E Networks | A+E Networks | A+E Networks | A+E Networks | A+E Networks |
| 23 | A+R | A+R | A+R | A+R | Disney | A+R | — | A+R | A+R | A+R | A+R | A+R | A+R | A+R | A+R |
| 24 | A-film | A-film | A-film | A-film | Lionsgate | A-film | — | A-film | A-film | A-film | A-film | A-film | A-film | A-film | A-film |
| 25 | AAA | AAA | AAA | AAA | A24 | AAA | — | AAA | AAA | AAA | AAA | AAA | AAA | AAA | AAA |
| 253 | Disney / Buena Vista | Disney | Disney / Buena Vista | Disney / Buena Vista | — | Disney / Buena Vista | — | Disney / Buena Vista | Disney / Buena Vista | Disney + | Disney / Buena Vista | Disney / Buena Vista | Disney / Buena Vista | Disney / Buena Vista | Disney / Buena Vista |
| 473 | Kinowelt Home Entertainment | Kinowelt Home Entertainment/DVD | Kinowelt Home Entertainment/DVD | Kinowelt Home Entertainment/DVD | — | Kinowelt Home Entertainment/DVD | — | Kinowelt Home Entertainment/DVD | Kinowelt Home Entertainment/DVD | Kinowelt Home Entertainment/DVD | Kinowelt Home Entertainment/DVD | Kinowelt Home Entertainment/DVD | Kinowelt Home Entertainment/DVD | Kinowelt Home Entertainment/DVD | Kinowelt Home Entertainment/DVD |
| 820 | Studio Canal | Studio Canal | StudioCanal | Studio Canal | — | Studio Canal | — | Studio Canal | Studio Canal | Studio Canal | Studio Canal | Studio Canal | Studio Canal | Studio Canal | Studio Canal |
| 966 | ABC Studios | ABC Studios | Plumeria Pictures | — | — | Altro | — | Deaf Crocodile | Level 33 Entertainment | PTTRiP | — | Radiance Films | Fandango | — | Crunchyroll, LLC |
| 967 | Plaion | ADV Films | Indicator | — | — | Universal Pictures | — | Rhino Home Video | A24 | Kadr | — | — | Universal Pictures Home Entertainment | — | Plaion Pictures |
| 968 | Crunchyroll, LLC | Arthaus | Crocofilms | — | — | Prime Video | — | US Manga Corps | — | Walt Disney Production | — | — | Warner Home Video | — | I Wonder Pictures |
| 969 | Cinématographe | ArtsMagic | Plaion | — | — | — | — | ADV Films | — | Prime ➡️ | — | — | Cecchi Gori Home Video | — | CG Entertainment |
| 970 | Chameleon Films | Bandai Entertainment | Hallmark | — | — | — | — | Crunchyroll | — | Studio Filmowe Perspektywa | — | — | Terminal Video | — | A24 |
| 971 | Decal Releasing | Canadian International Pictures | Arcadès | — | — | — | — | — | — | Telewizja Polska | — | — | CG Entertainment | — | Radiance Films |
| 972 | Saturn's Core Audio & Video | Celluloid Dreams | Clavis Films | — | — | — | — | — | — | Canal+ Polska | — | — | — | — | ADV Films |
| 973 | Radiance Films | Central Park Media | Decal Releasing | — | — | — | — | — | — | Dimension Films | — | — | — | — | Old Gold Media |
| 974 | Warner Archive Collection | Chameleon Films | Mayfly | — | — | — | — | — | — | Hanna-Barbera | — | — | — | — | — |
| 975 | Terror Vision | Channel One | Radiance Films | — | — | — | — | — | — | Cinerama | — | — | — | — | — |
| 976 | Celluloid Dreams | Chimera Entertainment | IndiePix Films | — | — | — | — | — | — | Universla release | — | — | — | — | — |
| 977 | Gabita Barbieri Films | Cinématographe | ND Play | — | — | — | — | — | — | Dino De Laurentiis | — | — | — | — | — |
| 978 | Canadian International Pictures | Crunchyroll, LLC | Cineriz | — | — | — | — | — | — | A24 | — | — | — | — | — |
| 979 | Dark Star Pictures | Dark Star Pictures | Cinematografica | — | — | — | — | — | — | Player | — | — | — | — | — |
| 980 | Level 33 Entertainment | Decal Releasing | Pierrot Le Fou | — | — | — | — | — | — | TVN | — | — | — | — | — |
| 981 | Arthaus | Error 4444 | Giant Interactive | — | — | — | — | — | — | Prime Video | — | — | — | — | — |
| 982 | Factory25 | Factory25 | Showshank Films | — | — | — | — | — | — | MAX | — | — | — | — | — |
| 983 | Indicator | Gabita Barbieri Films | TFC | — | — | — | — | — | — | Viaplay | — | — | — | — | — |
| 984 | Utopia Distribution | Indicator | A24 | — | — | — | — | — | — | Amazon Prime | — | — | — | — | — |
| 985 | Janson Media | Janson Media | Crunchyroll, LLC | — | — | — | — | — | — | TVP VOD | — | — | — | — | — |
| 986 | Lost Time Media | Joy Sales | Mediacs | — | — | — | — | — | — | TVP Sport | — | — | — | — | — |
| 987 | ADV Films | Level 33 Entertainment | Happy Entertainment | — | — | — | — | — | — | WP Pilot | — | — | — | — | — |
| 988 | Bandai Entertainment | Lost Time Media | Error 4444 | — | — | — | — | — | — | Megogo | — | — | — | — | — |
| 989 | Melusine | Melusine | Big World Pictures | — | — | — | — | — | — | Extreme+ | — | — | — | — | — |
| 990 | Central Park Media | Panik House | Cinématographe | — | — | — | — | — | — | Polsat Box Go | — | — | — | — | — |
| 991 | U.S. Manga Corps | Pioneer | September Film | — | — | — | — | — | — | HBO MAX | — | — | — | — | — |
| 992 | Cult Media | Plaion | Cinehollywood | — | — | — | — | — | — | Canal+ Online | — | — | — | — | — |
| 993 | Infinity Arthouse | Radiance Films | Re:Voir | — | — | — | — | — | — | Play Now | — | — | — | — | — |
| 994 | A24 | Rentrak | Warren Miller Entertainment | — | — | — | — | — | — | Televio | — | — | — | — | — |
| 995 | PolyGram Video | SamuraiDVD | Flashback Entertainment | — | — | — | — | — | — | Skyshowtime | — | — | — | — | — |
| 996 | VIZ Media, LLC | Saturn's Core Audio & Video | Survivance | — | — | — | — | — | — | Apple TV+ | — | — | — | — | — |
| 997 | Genius Entertainment | Terror Vision | Teton Gravity Research | — | — | — | — | — | — | CDA Premium | — | — | — | — | — |
| 998 | Artisan Home Entertainment | U.S. Manga Corps | Sphere Films | — | — | — | — | — | — | Rakuten | — | — | — | — | — |
| 999 | The Film Preserve | Urban Vision | Dauntless Studios | — | — | — | — | — | — | iTunes | — | — | — | — | — |
| 1000 | Lightbulb Film Distribution | Utopia Distribution | — | — | — | — | — | — | — | Ninateka | — | — | — | — | — |
| 1001 | Indeed Film | Warner Archive Collection | Cartuna | — | — | — | — | — | — | E-Kino Pod Baranami | — | — | — | — | — |
| 1002 | Old Gold Media | Whole Grain Pictures | Program Store | — | — | — | — | — | — | MOJEeKINO | — | — | — | — | — |
| 1003 | Cine Plus Home Entertainment | Afilm | Ryko Distribution | — | — | — | — | — | — | Nowe Horyzonty | — | — | — | — | — |
| 1004 | Patriot Films | Deaf Crocodile | Bleeding Skull | — | — | — | — | — | — | Pięć Smaków | — | — | — | — | — |
| 1005 | Terminal Video | Pathfinder Home Entertainment | Midnight Factory | — | — | — | — | — | — | VOD.MDAG.PL | — | — | — | — | — |
| 1006 | Sandpiper Pictures | Hong Kong Legends | ABC - (American Broadcasting Corporation) | — | — | — | — | — | — | Katoflix | — | — | — | — | — |
| 1007 | Ostalgica | Scholar Video | Hammer Films | — | — | — | — | — | — | Outfilm | — | — | — | — | — |
| 1008 | Distrimax | Buena Vista | Indeed Film | — | — | — | — | — | — | 35mm.online | — | — | — | — | — |
| 1009 | Planet Media Home Entertainment | — | SND | — | — | — | — | — | — | FlixClassic | — | — | — | — | — |
| 1010 | Numax | Kani Releasing | Vintage Classics | — | — | — | — | — | — | VOD Warszawa | — | — | — | — | — |
| 1011 | KimStim | Wonder Multimídia | Ostalgica | — | — | — | — | — | — | CHILI | — | — | — | — | — |
| 1012 | Pro-Fun Media | Anime Factory | Dark Star Pictures | — | — | — | — | — | — | RED GO | — | — | — | — | — |
| 1013 | Zorro Medien | Xenon | OneGate Media | — | — | — | — | — | — | ARTE po polsku | — | — | — | — | — |
| 1014 | Wild Bunch Benelux | KSM Anime | Distribpix | — | — | — | — | — | — | TVSmart | — | — | — | — | — |
| 1015 | Allumination FilmWorks | — | Level 33 Entertainment | — | — | — | — | — | — | FAME MMA | — | — | — | — | — |
| 1016 | New Line Home Video | — | Shoreline Entertainment | — | — | — | — | — | — | CLOUT MMA | — | — | — | — | — |
| 1017 | Cloud Ten Pictures | — | WMM | — | — | — | — | — | — | PRIME MMA | — | — | — | — | — |
| 1018 | Kinowelt Film Entertainment | — | Source 1 Media B.V. | — | — | — | — | — | — | KSW | — | — | — | — | — |
| 1019 | Visual Vengeance | — | Criterion Collection - Criterion Premieres | — | — | — | — | — | — | IPLA VOD | — | — | — | — | — |
| 1020 | Senator Home Entertainment | — | ETR Media | — | — | — | — | — | — | Kino Polska TV | — | — | — | — | — |
| 1021 | Toy Robot Video | — | Yellow Veil Pictures | — | — | — | — | — | — | — | — | — | — | — | — |
| 1022 | Modern Films | — | Alpha Video | — | — | — | — | — | — | — | — | — | — | — | — |
| 1023 | POLAR Film | — | Terror Vision | — | — | — | — | — | — | — | — | — | — | — | — |
| 1024 | Medien | — | Black Bear | — | — | — | — | — | — | — | — | — | — | — | — |

BLUTOPIA distinguishes `StudioCanal` (820) and `Studio Canal` (1184). Its canonical `Studio Canal` entry takes precedence over the upstream spelling for ID 820.

## Recognized names without an upstream ID

UA’s broader name recognition list is separate from upload IDs. Being recognized does not imply an upstream or tracker ID exists.

417 recognized names have no default mapping. Their upload IDs are only available where a tracker snapshot defines them.

| Name | Trackers defining this name |
|---|---|
| 1091 | BLUTOPIA |
| 2GOOD | BLUTOPIA |
| A24 | AITHER, BLUTOPIA, HAWKEUNO, ONLYENCODES, POLISHTORRENT, ULCX |
| AAMU FILM COMPANY | BLUTOPIA |
| ABC - (AMERICAN BROADCASTING CORPORATION) | BLUTOPIA |
| ABC STUDIOS | AITHER, ASIANCINEMA |
| ACME FILM | BLUTOPIA |
| ADV FILMS | AITHER, ASIANCINEMA, BLUTOPIA, OLDTOONSWORLD, ULCX |
| ALLIED VAUGHN | BLUTOPIA |
| ALLUMINATION FILMWORKS | AITHER |
| ALPHA VIDEO | BLUTOPIA |
| ANDERSON MERCHANDISE | BLUTOPIA |
| ANTI-WORLDS | BLUTOPIA |
| ARCADE VIDEO | BLUTOPIA |
| ARCADÈS | BLUTOPIA |
| ARIZTICAL ENTERTAINMENT | BLUTOPIA |
| ARTHAUS | AITHER, ASIANCINEMA, BLUTOPIA |
| ARTISAN | BLUTOPIA |
| ARTISAN HOME ENTERTAINMENT | AITHER |
| ARTISTA FILMI | BLUTOPIA |
| ASIAN FILM ARCHIVE | BLUTOPIA |
| ATALANTA FILMES | BLUTOPIA |
| ATHENA | BLUTOPIA |
| ATLANTICFILM | BLUTOPIA |
| ATTRACTION DISTRIBUTION | BLUTOPIA |
| AUD | BLUTOPIA |
| AVH | BLUTOPIA |
| B-SPREE CLASSICS | BLUTOPIA |
| BANDAI ENTERTAINMENT | AITHER, ASIANCINEMA, BLUTOPIA |
| BAYVIEW | BLUTOPIA |
| BEL CANTO | BLUTOPIA |
| BIG WORLD PICTURES | BLUTOPIA |
| BIM | BLUTOPIA |
| BLACK BEAR | BLUTOPIA |
| BLEEDING SKULL | BLUTOPIA |
| BLUE WATER CONTENT | BLUTOPIA |
| BLUEBELL FILMS | BLUTOPIA |
| BOUNTY FILMS | BLUTOPIA |
| BRENTWOOD | BLUTOPIA |
| BRETZ FILMES | BLUTOPIA |
| BRITISH HOME ENTERTAINMENT | BLUTOPIA |
| BURNING BULB PRODUCTIONS | BLUTOPIA |
| CAHIERS DU CINÉMA | BLUTOPIA |
| CANADIAN INTERNATIONAL PICTURES | AITHER, ASIANCINEMA, BLUTOPIA |
| CARDINAL RELEASING | BLUTOPIA |
| CARLTON | BLUTOPIA |
| CARTUNA | BLUTOPIA |
| CATCOM HOME VIDEO | BLUTOPIA |
| CATTLEYA | BLUTOPIA |
| CDI | BLUTOPIA |
| CELLULOID DREAMS | AITHER, ASIANCINEMA |
| CENTRAL PARK MEDIA | AITHER, ASIANCINEMA, BLUTOPIA |
| CENTRE AUDIOVISUEL SIMONE DE BEAUVOIR | BLUTOPIA |
| CG ENTERTAINMENT | BLUTOPIA, SHAREISLAND, ULCX |
| CHAMELEON FILMS | AITHER, ASIANCINEMA, BLUTOPIA |
| CHANNEL 4 | BLUTOPIA |
| CHRISTAL FILMS | BLUTOPIA |
| CHRYSTAL FILMS | BLUTOPIA |
| CINE PLUS HOME ENTERTAINMENT | AITHER |
| CINECOM | BLUTOPIA |
| CINEHOLLYWOOD | BLUTOPIA |
| CINELICIOUS PICS | BLUTOPIA |
| CINEMA CLUB | BLUTOPIA |
| CINEMAGI | BLUTOPIA |
| CINEMATOGRAFICA | BLUTOPIA |
| CINEPHOBIA RELEASING | BLUTOPIA |
| CINERIZ | BLUTOPIA |
| CINÉMATOGRAPHE | AITHER, ASIANCINEMA, BLUTOPIA |
| CLAVIS FILMS | BLUTOPIA |
| CLOUD TEN PICTURES | AITHER |
| CMF | BLUTOPIA |
| CNN | BLUTOPIA |
| COLORED FILMS | BLUTOPIA |
| COMMAND VIDEO | BLUTOPIA |
| CONTENDER ENTERTAINMENT GROUP | BLUTOPIA |
| CORINTH FILMS | BLUTOPIA |
| CRASH CINEMA | BLUTOPIA |
| CRISTALDI FILM | BLUTOPIA |
| CRITERION COLLECTION - CRITERION PREMIERES | BLUTOPIA |
| CROCOFILMS | BLUTOPIA |
| CRUNCHYROLL, LLC | AITHER, ASIANCINEMA, BLUTOPIA, ULCX |
| CULT MEDIA | AITHER |
| D & D GLASS AND WYATT | BLUTOPIA |
| DAIEI | BLUTOPIA |
| DARK SKY FILMS | BLUTOPIA |
| DARK STAR PICTURES | AITHER, ASIANCINEMA, BLUTOPIA |
| DAUNTLESS STUDIOS | BLUTOPIA |
| DAVID BURTON MORRIS FILMS | BLUTOPIA |
| DD HOME ENTERTAINMENT | BLUTOPIA |
| DEAF CROCODILE | ASIANCINEMA, BLUTOPIA, OLDTOONSWORLD |
| DECAL RELEASING | AITHER, ASIANCINEMA, BLUTOPIA |
| DEGAUSSER VIDEO | BLUTOPIA |
| DEKANALOG | BLUTOPIA |
| DIGITAL CLASSICS | BLUTOPIA |
| DIGITAL ELEMENT | BLUTOPIA |
| DIGITAL MEME | BLUTOPIA |
| DISTRIB FILMS | BLUTOPIA |
| DISTRIBPIX | BLUTOPIA |
| DISTRIMAX | AITHER |
| DOCURAMA | BLUTOPIA |
| DOMINO FILM | BLUTOPIA |
| DORIANE FILMS | BLUTOPIA |
| DREAMSCAPE | BLUTOPIA |
| DVD POCKET | BLUTOPIA |
| EASTWIND FILMS | BLUTOPIA |
| EDICIONES 79 | BLUTOPIA |
| EDITION FILMMUSEUM | BLUTOPIA |
| EDITO FILMS | BLUTOPIA |
| EESTI FILM 100 | BLUTOPIA |
| ELEMENT PICTURES | BLUTOPIA |
| ELITE ENTERTAINMENT | BLUTOPIA |
| ELOKUVAPALVELU J. SUOMALAINEN | BLUTOPIA |
| EMBREM ENTERTAINMENT | BLUTOPIA |
| ENCORE | BLUTOPIA |
| EPELPOL | BLUTOPIA |
| EPF MEDIA | BLUTOPIA |
| EPICENTRE FILMS | BLUTOPIA |
| ERROR 4444 | ASIANCINEMA, BLUTOPIA |
| ETR MEDIA | BLUTOPIA |
| EUREKA - MASTERS OF CINEMA | BLUTOPIA |
| EUSTON HOME ENTERTAINMENT | BLUTOPIA |
| FACETS | BLUTOPIA |
| FACTORY25 | AITHER, ASIANCINEMA, BLUTOPIA |
| FANDANGO | BLUTOPIA, SHAREISLAND |
| FANTOMA | BLUTOPIA |
| FEEL FILMS | BLUTOPIA |
| FILM 2000 | BLUTOPIA |
| FILM FOETUS | BLUTOPIA |
| FILM MASTERS | BLUTOPIA |
| FILM PRESERVATION SOCIETY | BLUTOPIA |
| FILMBUFF | BLUTOPIA |
| FILMGALERIE 451 | BLUTOPIA |
| FILMHUB | BLUTOPIA |
| FILMNATION ENTERTAINMENT | BLUTOPIA |
| FILMOTECA ESPAÑOLA | BLUTOPIA |
| FILMOTRONIK | BLUTOPIA |
| FILMS SANS FRONTIERES | BLUTOPIA |
| FINNKINO | BLUTOPIA |
| FIRST RUN FEATURES | BLUTOPIA |
| FLASHBACK ENTERTAINMENT | BLUTOPIA |
| FLASHSTAR HOME ENTERTAINMENT | BLUTOPIA |
| FOLKETS BIO | BLUTOPIA |
| FOX LORBER | BLUTOPIA |
| FRACTURED VISIONS | BLUTOPIA |
| FRAMEHAMMER FILMS | BLUTOPIA |
| FRAMELINE | BLUTOPIA |
| FUTURAMA | BLUTOPIA |
| GABITA BARBIERI FILMS | AITHER, ASIANCINEMA, BLUTOPIA |
| GEMINI VIDÉO EDITIONS | BLUTOPIA |
| GENIUS ENTERTAINMENT | AITHER, BLUTOPIA |
| GIANT INTERACTIVE | BLUTOPIA |
| GLOBAL FILM | BLUTOPIA |
| GLOBO FILMES | BLUTOPIA |
| GLOBUS GROUP | BLUTOPIA |
| GOLDHIL VIDEO | BLUTOPIA |
| GOOD GUYS MEDIA | BLUTOPIA |
| GOOD TIMES | BLUTOPIA |
| GROUP GENDAI FILMS | BLUTOPIA |
| GZBEAUTY | BLUTOPIA |
| HALLMARK | BLUTOPIA |
| HAMMER FILMS | BLUTOPIA |
| HAPPY ENTERTAINMENT | BLUTOPIA |
| HARDY CLASSIC VIDEO | BLUTOPIA |
| HART SHARP | BLUTOPIA |
| HD CINEMA CLASSICS | BLUTOPIA |
| HIP-O RECORDS | BLUTOPIA |
| HOLLYWOOD DVD | BLUTOPIA |
| HOME MOVIES | BLUTOPIA |
| HOME VISION ENTERTAINMENT | BLUTOPIA |
| ICA | BLUTOPIA |
| ICARUS FILMS | BLUTOPIA |
| IGNITE FILMS | BLUTOPIA |
| ILLUME | BLUTOPIA |
| ILLUMINATIONS | BLUTOPIA |
| IMAGINE FILM DISTRIBUTION | BLUTOPIA |
| IMMINA FILMS | BLUTOPIA |
| IMPULSE PICTURES | BLUTOPIA |
| IMPULSO | BLUTOPIA |
| INDEED FILM | AITHER, BLUTOPIA |
| INDICATOR | AITHER, ASIANCINEMA, BLUTOPIA, HAWKEUNO |
| INDIEPIX FILMS | BLUTOPIA |
| INDIES ENTERTAINMENT | BLUTOPIA |
| INFINITY ARTHOUSE | AITHER, BLUTOPIA |
| INFINITY ENTERTAINMENT | BLUTOPIA |
| INTERESTING FILMS DIFFERENT PERSPECTIVES | BLUTOPIA |
| INTERNATIONAL SAMI FILM INSTITUTE | BLUTOPIA |
| ISLA SALES | BLUTOPIA |
| ISRAELI FILM FUND | BLUTOPIA |
| ISTITUTO LUCE | BLUTOPIA |
| ITV STUDIOS HOME ENTERTAINMENT | BLUTOPIA |
| JANSON MEDIA | AITHER, ASIANCINEMA |
| JANUS FILMS | BLUTOPIA |
| JOY SALES | ASIANCINEMA, BLUTOPIA |
| JUPITER | BLUTOPIA |
| KANI | BLUTOPIA |
| KIDDIEPUNK | BLUTOPIA |
| KIMSTIM | AITHER, BLUTOPIA |
| KINOVISTA | BLUTOPIA |
| KINOWELT FILM ENTERTAINMENT | AITHER |
| KOREAN FILM ARCHIVE | BLUTOPIA |
| KRUPNYY PLAN | BLUTOPIA |
| KUMAR FILMS | BLUTOPIA |
| LA ENTERTAINMENT | BLUTOPIA |
| LA RABBIA | BLUTOPIA |
| LA TRAVERSE | BLUTOPIA |
| LA VIE EST BELLE | BLUTOPIA |
| LANCE ENTERTAINMENT | BLUTOPIA |
| LAVA | BLUTOPIA |
| LES DOCUMENTS CINÉMATOGRAPHIQUES | BLUTOPIA |
| LES FILMS DE MA VIE | BLUTOPIA |
| LES FILMS DU 3 MARS | BLUTOPIA |
| LES FILMS DU CAMÉLIA | BLUTOPIA |
| LES FILMS DU PARADOXE | BLUTOPIA |
| LEVEL 1 PRODUCTIONS | BLUTOPIA |
| LEVEL 33 ENTERTAINMENT | AITHER, ASIANCINEMA, BLUTOPIA, ONLYENCODES |
| LIBERATION ENTERTAINMENT | BLUTOPIA |
| LIBERATION HALL | BLUTOPIA |
| LIGHTBULB FILM DISTRIBUTION | AITHER, BLUTOPIA |
| LOOKOUT MOUNTAIN STUDIO | BLUTOPIA |
| LOST TIME MEDIA | AITHER, ASIANCINEMA |
| LUMIMIESFILMI | BLUTOPIA |
| LUSOMUNDO | BLUTOPIA |
| MADACY ENTERTAINMENT | BLUTOPIA |
| MAISON4TIERS | BLUTOPIA |
| MAKE PEACE PRODUCTONS | BLUTOPIA |
| MALAVIDA | BLUTOPIA |
| MANGA CORPS | BLUTOPIA |
| MANGA FILMS | BLUTOPIA |
| MARFILMES | BLUTOPIA |
| MASTERS OF CINEMA | None of the supplied snapshots |
| MAWU FILMS | BLUTOPIA |
| MAYFLY | BLUTOPIA |
| MCINTYRE MEDIA INC | BLUTOPIA |
| MEDIABOOK | BLUTOPIA |
| MEDIACS | BLUTOPIA |
| MEDIEN | AITHER |
| MELUSINE | AITHER, ASIANCINEMA |
| MEMORY | BLUTOPIA |
| MHZ | BLUTOPIA |
| MICROCINEMA | BLUTOPIA |
| MIDNIGHT FACTORY | BLUTOPIA |
| MIKADO | BLUTOPIA |
| MILLENNIUM STORM | BLUTOPIA |
| MIS LABEL | BLUTOPIA |
| MOC | None of the supplied snapshots |
| MODERN FILMS | AITHER, BLUTOPIA |
| MOKÉP | BLUTOPIA |
| MOLOT ENTERTAINMENT | BLUTOPIA |
| MONARCH HOME ENTERTAINMENT | BLUTOPIA |
| MONDO HOME ENTERTAINMENT (ITALY) | BLUTOPIA |
| MORE ENTERTAINMENT | BLUTOPIA |
| MUNDO EN DVD | BLUTOPIA |
| MUSICTRONIC ENTERTAINMENT | BLUTOPIA |
| MYA | BLUTOPIA |
| NATIONAL FILM BOARD OF CANADA | BLUTOPIA |
| NBC HOME VIDEO | BLUTOPIA |
| ND PLAY | BLUTOPIA |
| NEON | BLUTOPIA |
| NEW LINE HOME VIDEO | AITHER |
| NEW STAR | BLUTOPIA |
| NEW VIDEO | BLUTOPIA |
| NEW YORKER FILMS | BLUTOPIA |
| NGI | BLUTOPIA |
| NIGHT VISIONS | BLUTOPIA |
| NIKKATSU | BLUTOPIA |
| NMC UNITED ENTERTAINMENT | BLUTOPIA |
| NO SHAME FILMS | BLUTOPIA |
| NORMA PRODUCTIONS | BLUTOPIA |
| NOVY DISK | BLUTOPIA |
| NU BOYANA | BLUTOPIA |
| NUMAX | AITHER |
| OBLIVION | BLUTOPIA |
| ODYSSEY | BLUTOPIA |
| ODYSSEY QUEST | BLUTOPIA |
| OLD GOLD MEDIA | AITHER, ULCX |
| OLYDRI | BLUTOPIA |
| ON AIR | BLUTOPIA |
| ONEGATE MEDIA | BLUTOPIA |
| OPTIMALE | BLUTOPIA |
| OPTIMUM WORLD | BLUTOPIA |
| OSTALGICA | AITHER, BLUTOPIA |
| OUTCAST FILMS | BLUTOPIA |
| P.O.M. FILMS | BLUTOPIA |
| PALM PICTURES | BLUTOPIA |
| PANIK HOUSE | ASIANCINEMA, BLUTOPIA |
| PASSPORT VIDEO | BLUTOPIA |
| PATHFINDER HOME ENTERTAINMENT | ASIANCINEMA, BLUTOPIA |
| PATRIOT FILMS | AITHER |
| PAYLESS ENTERTAINMENT LIMITED | BLUTOPIA |
| PERISCOPE FILM | BLUTOPIA |
| PICTURE THIS | BLUTOPIA |
| PIERROT LE FOU | BLUTOPIA |
| PIONEER | ASIANCINEMA, BLUTOPIA |
| PLAION | AITHER, ASIANCINEMA, BLUTOPIA |
| PLAN B | BLUTOPIA |
| PLANET DVD | BLUTOPIA |
| PLANET MEDIA HOME ENTERTAINMENT | AITHER |
| PLATINUM DISC | BLUTOPIA |
| PLEXIFILM | BLUTOPIA |
| PLUMERIA PICTURES | BLUTOPIA |
| POLAR FILM | AITHER |
| POLYGRAM | BLUTOPIA |
| POLYGRAM VIDEO | AITHER |
| PRECISION PICTURES | BLUTOPIA |
| PRO-FUN MEDIA | AITHER |
| PROGRAM STORE | BLUTOPIA |
| RABINOVICH FOUNDATION | BLUTOPIA |
| RADIANCE FILMS | AITHER, ASIANCINEMA, BLUTOPIA, REELFLIX, ULCX |
| RAI − RADIOTELEVISIONE ITALIANA | BLUTOPIA |
| RE:VOIR | BLUTOPIA |
| RED BULL MEDIA HOUSE | BLUTOPIA |
| REEL ROCK | BLUTOPIA |
| REELIN' IN THE YEARS | BLUTOPIA |
| REFRESH | BLUTOPIA |
| RENOWN | BLUTOPIA |
| RENÉ CHATEAU VIDEO | BLUTOPIA |
| REPUBLIC PICTURES | BLUTOPIA |
| RETRO GOLD 63 | BLUTOPIA |
| RHI | BLUTOPIA |
| ROUTE ONE RELEASING | BLUTOPIA |
| RUSCICO | BLUTOPIA |
| RUSTBLADE | BLUTOPIA |
| RYKO DISTRIBUTION | BLUTOPIA |
| RYKODISC | BLUTOPIA |
| SABOTAKT | BLUTOPIA |
| SALZGEBER & CO. | BLUTOPIA |
| SANCTUARY RECORDS | BLUTOPIA |
| SANDPIPER PICTURES | AITHER, BLUTOPIA |
| SATURN'S CORE AUDIO & VIDEO | AITHER, ASIANCINEMA |
| SCANTRADE | BLUTOPIA |
| SCREEN ARCHIVES ENTERTAINMENT | BLUTOPIA |
| SENATOR HOME ENTERTAINMENT | AITHER |
| SEPTEMBER FILM | BLUTOPIA |
| SEVEN SPRINGS PICTURES | BLUTOPIA |
| SHANACHIE | BLUTOPIA |
| SHELLAC | BLUTOPIA |
| SHORELINE ENTERTAINMENT | BLUTOPIA |
| SHOWSHANK FILMS | BLUTOPIA |
| SIMPLY MEDIA | BLUTOPIA |
| SLAM DUNK MEDIA | BLUTOPIA |
| SLOVENIAN FILM CENTRE | BLUTOPIA |
| SMORE ENTERTAINMENT | BLUTOPIA |
| SND | BLUTOPIA |
| SOGEMEDIA | BLUTOPIA |
| SOGEPAQ | BLUTOPIA |
| SOMETHING WEIRD | BLUTOPIA |
| SOURCE 1 MEDIA B.V. | BLUTOPIA |
| SOVEREIGN FILM | BLUTOPIA |
| SPHERE FILMS | BLUTOPIA |
| SPROCKET VAULT | BLUTOPIA |
| STONE LANTERN FILMS | BLUTOPIA |
| STRADA FILM | BLUTOPIA |
| STRAWBERRY MEDIA | BLUTOPIA |
| STUDIO 24 | BLUTOPIA |
| STUDIO DISTRIBUTION SERVICES | BLUTOPIA |
| STUDIOCANAL | BLUTOPIA |
| SUB ROSA | BLUTOPIA |
| SUBVERSIVE CINEMA | BLUTOPIA |
| SULLIVAN ENTERTAINMENT | BLUTOPIA |
| SUNDANCE | BLUTOPIA |
| SURF VIDEO | BLUTOPIA |
| SURVIVANCE | BLUTOPIA |
| TABU | BLUTOPIA |
| TAIWAN FILM INSTITUTE | BLUTOPIA |
| TANELORN FILMS | BLUTOPIA |
| TANGO ENTERTAINMENT | BLUTOPIA |
| TARTAN VIDEO | BLUTOPIA |
| TELEVISTA | BLUTOPIA |
| TERMINAL VIDEO | AITHER, SHAREISLAND |
| TERROR VISION | AITHER, ASIANCINEMA, BLUTOPIA |
| TETON GRAVITY RESEARCH | BLUTOPIA |
| TFC | BLUTOPIA |
| TGG DIRECT | BLUTOPIA |
| THAI FILM ARCHIVE | BLUTOPIA |
| THANK U INTERNATIONAL CO., LTD. | BLUTOPIA |
| THE FILM DESK | BLUTOPIA |
| THE FILM PRESERVE | AITHER, BLUTOPIA |
| THE THIRD EAR | BLUTOPIA |
| THINKFILM | BLUTOPIA |
| TOY ROBOT VIDEO | AITHER |
| TRANSFORMER | BLUTOPIA |
| TREASURED FILMS | BLUTOPIA |
| TRIBECA | BLUTOPIA |
| TRIMARK | BLUTOPIA |
| TYPECAST RELEASING | BLUTOPIA |
| U.S. MANGA CORPS | AITHER, ASIANCINEMA |
| UFO DISTRIBUTION | BLUTOPIA |
| UNDERCRANK PRODUCTIONS | BLUTOPIA |
| UNITED KING FILMS | BLUTOPIA |
| UTOPIA DISTRIBUTION | AITHER, ASIANCINEMA, BLUTOPIA |
| VAI | BLUTOPIA |
| VANGUARD | BLUTOPIA |
| VIDANGEL STUDIOS | BLUTOPIA |
| VIDEO PROJECT | BLUTOPIA |
| VIDEODIS | BLUTOPIA |
| VIEW VIDEO | BLUTOPIA |
| VINCA FILM | BLUTOPIA |
| VINTAGE CLASSICS | BLUTOPIA |
| VIPCO | BLUTOPIA |
| VISION FILM (POLAND) | BLUTOPIA |
| VISION VIDEO UK | BLUTOPIA |
| VISUAL VENGEANCE | AITHER |
| VIZ MEDIA, LLC | AITHER |
| VÉRTICE CINE | BLUTOPIA |
| WARREN MILLER ENTERTAINMENT | BLUTOPIA |
| WATER BEARER FILMS | BLUTOPIA |
| WELLSPRING | BLUTOPIA |
| WHITE PINE PICTURES | BLUTOPIA |
| WILD BUNCH BENELUX | AITHER |
| WILD EAST | BLUTOPIA |
| WINSTAR | BLUTOPIA |
| WMM | BLUTOPIA |
| XENON | ASIANCINEMA, BLUTOPIA |
| YELLOW VEIL PICTURES | BLUTOPIA |
| YUME PICTURES | BLUTOPIA |
| ZILLION FILM | BLUTOPIA |
| ZORRO MEDIEN | AITHER |

## Tracker names absent from UA’s recognition list

Preparation preserves these names through its fallback; their tracker-specific IDs resolve directly.

| Tracker | ID | Name |
|---|---:|---|
| ASIANCINEMA | 969 | ArtsMagic |
| ASIANCINEMA | 975 | Channel One |
| ASIANCINEMA | 976 | Chimera Entertainment |
| ASIANCINEMA | 994 | Rentrak |
| ASIANCINEMA | 995 | SamuraiDVD |
| ASIANCINEMA | 999 | Urban Vision |
| ASIANCINEMA | 1002 | Whole Grain Pictures |
| ASIANCINEMA | 1003 | Afilm |
| ASIANCINEMA | 1006 | Hong Kong Legends |
| ASIANCINEMA | 1007 | Scholar Video |
| ASIANCINEMA | 1010 | Kani Releasing |
| ASIANCINEMA | 1011 | Wonder Multimídia |
| ASIANCINEMA | 1012 | Anime Factory |
| ASIANCINEMA | 1014 | KSM Anime |
| HAWKEUNO | 3 | Arrow Video |
| HAWKEUNO | 8 | Second Sight Films |
| HAWKEUNO | 17 | Scream Factory |
| HAWKEUNO | 21 | Universal Pictures |
| ITATORRENTS | 966 | Altro |
| ITATORRENTS | 967 | Universal Pictures |
| ITATORRENTS | 968 | Prime Video |
| OLDTOONSWORLD | 967 | Rhino Home Video |
| OLDTOONSWORLD | 968 | US Manga Corps |
| OLDTOONSWORLD | 970 | Crunchyroll |
| POLISHTORRENT | 253 | Disney + |
| POLISHTORRENT | 966 | PTTRiP |
| POLISHTORRENT | 967 | Kadr |
| POLISHTORRENT | 968 | Walt Disney Production |
| POLISHTORRENT | 969 | Prime ➡️ |
| POLISHTORRENT | 970 | Studio Filmowe Perspektywa |
| POLISHTORRENT | 971 | Telewizja Polska |
| POLISHTORRENT | 972 | Canal+ Polska |
| POLISHTORRENT | 973 | Dimension Films |
| POLISHTORRENT | 974 | Hanna-Barbera |
| POLISHTORRENT | 975 | Cinerama |
| POLISHTORRENT | 976 | Universla release |
| POLISHTORRENT | 977 | Dino De Laurentiis |
| POLISHTORRENT | 979 | Player |
| POLISHTORRENT | 980 | TVN |
| POLISHTORRENT | 981 | Prime Video |
| POLISHTORRENT | 982 | MAX |
| POLISHTORRENT | 983 | Viaplay |
| POLISHTORRENT | 984 | Amazon Prime |
| POLISHTORRENT | 985 | TVP VOD |
| POLISHTORRENT | 986 | TVP Sport |
| POLISHTORRENT | 987 | WP Pilot |
| POLISHTORRENT | 988 | Megogo |
| POLISHTORRENT | 989 | Extreme+ |
| POLISHTORRENT | 990 | Polsat Box Go |
| POLISHTORRENT | 991 | HBO MAX |
| POLISHTORRENT | 992 | Canal+ Online |
| POLISHTORRENT | 993 | Play Now |
| POLISHTORRENT | 994 | Televio |
| POLISHTORRENT | 995 | Skyshowtime |
| POLISHTORRENT | 996 | Apple TV+ |
| POLISHTORRENT | 997 | CDA Premium |
| POLISHTORRENT | 998 | Rakuten |
| POLISHTORRENT | 999 | iTunes |
| POLISHTORRENT | 1000 | Ninateka |
| POLISHTORRENT | 1001 | E-Kino Pod Baranami |
| POLISHTORRENT | 1002 | MOJEeKINO |
| POLISHTORRENT | 1003 | Nowe Horyzonty |
| POLISHTORRENT | 1004 | Pięć Smaków |
| POLISHTORRENT | 1005 | VOD.MDAG.PL |
| POLISHTORRENT | 1006 | Katoflix |
| POLISHTORRENT | 1007 | Outfilm |
| POLISHTORRENT | 1008 | 35mm.online |
| POLISHTORRENT | 1009 | FlixClassic |
| POLISHTORRENT | 1010 | VOD Warszawa |
| POLISHTORRENT | 1011 | CHILI |
| POLISHTORRENT | 1012 | RED GO |
| POLISHTORRENT | 1013 | ARTE po polsku |
| POLISHTORRENT | 1014 | TVSmart |
| POLISHTORRENT | 1015 | FAME MMA |
| POLISHTORRENT | 1016 | CLOUT MMA |
| POLISHTORRENT | 1017 | PRIME MMA |
| POLISHTORRENT | 1018 | KSW |
| POLISHTORRENT | 1019 | IPLA VOD |
| POLISHTORRENT | 1020 | Kino Polska TV |
| SHAREISLAND | 967 | Universal Pictures Home Entertainment |
| SHAREISLAND | 968 | Warner Home Video |
| SHAREISLAND | 969 | Cecchi Gori Home Video |
| ULCX | 967 | Plaion Pictures |
| ULCX | 968 | I Wonder Pictures |
