ä
T/Volumes/Mac OS Extended 1/riparian-poc/RiparianPoc.Api/Services/IGeoDataServices.cs
	namespace 	
RiparianPoc
 
. 
Api 
. 
Services "
;" #
public		 
	interface		  
ISpatialQueryService		 %
{

 
Task 
< 	
FeatureCollection	 
> 
GetStreamsAsync +
(+ ,
CancellationToken, =
ct> @
)@ A
;A B
Task 
< 	
FeatureCollection	 
> 
GetBuffersAsync +
(+ ,
CancellationToken, =
ct> @
)@ A
;A B
Task 
< 	
FeatureCollection	 
> 
GetParcelsAsync +
(+ ,
CancellationToken, =
ct> @
)@ A
;A B
Task 
< 	
FeatureCollection	 
> 
GetFocusAreasAsync .
(. /
CancellationToken/ @
ctA C
)C D
;D E
} 
public 
	interface "
IComplianceDataService '
{ 
Task 
< 	
IReadOnlyList	 
< 
VegetationReading (
>( )
>) *&
GetVegetationByBufferAsync+ E
(E F
int 
bufferId 
, 
CancellationToken '
ct( *
)* +
;+ ,
Task"" 
<"" 	
IReadOnlyList""	 
<"" 
ComplianceSummary"" (
>""( )
>"") *
GetSummaryAsync""+ :
("": ;
CancellationToken""; L
ct""M O
)""O P
;""P Q
}## Æd
S/Volumes/Mac OS Extended 1/riparian-poc/RiparianPoc.Api/Services/GeoDataServices.cs
	namespace 	
RiparianPoc
 
. 
Api 
. 
Services "
;" #
public 
sealed 
class 
SpatialQueryService '
:( ) 
ISpatialQueryService* >
{ 
private 
const 
string 
FeatureCountTag (
=) *
$str+ A
;A B
private 
static 
readonly 
ActivitySource *
Source+ 1
=2 3
new4 7
(7 8
$str8 V
)V W
;W X
private 
readonly 
IPostGisRepository '
_repository( 3
;3 4
private 
readonly 
ILogger 
< 
SpatialQueryService 0
>0 1
_logger2 9
;9 :
public 

SpatialQueryService 
( 
IPostGisRepository 

repository %
,% &
ILogger' .
<. /
SpatialQueryService/ B
>B C
loggerD J
)J K
{ 
_repository 
= 

repository  
??! #
throw$ )
new* -!
ArgumentNullException. C
(C D
nameofD J
(J K

repositoryK U
)U V
)V W
;W X
_logger 
= 
logger 
?? 
throw !
new" %!
ArgumentNullException& ;
(; <
nameof< B
(B C
loggerC I
)I J
)J K
;K L
} 
public 

async 
Task 
< 
FeatureCollection '
>' (
GetStreamsAsync) 8
(8 9
CancellationToken9 J
ctK M
)M N
{ 
using 
var 
activity 
= 
Source #
.# $
StartActivity$ 1
(1 2
$str2 K
)K L
;L M
_logger   
.   
LogInformation   
(   
$str   O
)  O P
;  P Q
const"" 
string"" 
sql"" 
="" 
$str"' 
;'' 
var)) 
fc)) 
=)) 
await)) 
_repository)) "
.))" #
QueryGeoJsonAsync))# 4
())4 5
sql))5 8
,))8 9
null)): >
,))> ?
ct))@ B
)))B C
;))C D
activity++ 
?++ 
.++ 
SetTag++ 
(++ 
FeatureCountTag++ (
,++( )
fc++* ,
.++, -
Count++- 2
)++2 3
;++3 4
_logger,, 
.,, 
LogInformation,, 
(,, 
$str,, T
,,,T U
fc,,V X
.,,X Y
Count,,Y ^
),,^ _
;,,_ `
return.. 
fc.. 
;.. 
}// 
public22 

async22 
Task22 
<22 
FeatureCollection22 '
>22' (
GetBuffersAsync22) 8
(228 9
CancellationToken229 J
ct22K M
)22M N
{33 
using44 
var44 
activity44 
=44 
Source44 #
.44# $
StartActivity44$ 1
(441 2
$str442 K
)44K L
;44L M
_logger66 
.66 
LogInformation66 
(66 
$str66 M
)66M N
;66N O
const88 
string88 
sql88 
=88 
$str8> 
;>> 
var@@ 
fc@@ 
=@@ 
await@@ 
_repository@@ "
.@@" #
QueryGeoJsonAsync@@# 4
(@@4 5
sql@@5 8
,@@8 9
null@@: >
,@@> ?
ct@@@ B
)@@B C
;@@C D
activityBB 
?BB 
.BB 
SetTagBB 
(BB 
FeatureCountTagBB (
,BB( )
fcBB* ,
.BB, -
CountBB- 2
)BB2 3
;BB3 4
_loggerCC 
.CC 
LogInformationCC 
(CC 
$strCC R
,CCR S
fcCCT V
.CCV W
CountCCW \
)CC\ ]
;CC] ^
returnEE 
fcEE 
;EE 
}FF 
publicII 

asyncII 
TaskII 
<II 
FeatureCollectionII '
>II' (
GetParcelsAsyncII) 8
(II8 9
CancellationTokenII9 J
ctIIK M
)IIM N
{JJ 
usingKK 
varKK 
activityKK 
=KK 
SourceKK #
.KK# $
StartActivityKK$ 1
(KK1 2
$strKK2 K
)KKK L
;KKL M
_loggerMM 
.MM 
LogInformationMM 
(MM 
$strMM H
)MMH I
;MMI J
constOO 
stringOO 
sqlOO 
=OO 
$strOV 
;VV 
varXX 
fcXX 
=XX 
awaitXX 
_repositoryXX "
.XX" #
QueryGeoJsonAsyncXX# 4
(XX4 5
sqlXX5 8
,XX8 9
nullXX: >
,XX> ?
ctXX@ B
)XXB C
;XXC D
activityZZ 
?ZZ 
.ZZ 
SetTagZZ 
(ZZ 
FeatureCountTagZZ (
,ZZ( )
fcZZ* ,
.ZZ, -
CountZZ- 2
)ZZ2 3
;ZZ3 4
_logger[[ 
.[[ 
LogInformation[[ 
([[ 
$str[[ I
,[[I J
fc[[K M
.[[M N
Count[[N S
)[[S T
;[[T U
return]] 
fc]] 
;]] 
}^^ 
publicaa 

asyncaa 
Taskaa 
<aa 
FeatureCollectionaa '
>aa' (
GetFocusAreasAsyncaa) ;
(aa; <
CancellationTokenaa< M
ctaaN P
)aaP Q
{bb 
usingcc 
varcc 
activitycc 
=cc 
Sourcecc #
.cc# $
StartActivitycc$ 1
(cc1 2
$strcc2 N
)ccN O
;ccO P
_loggeree 
.ee 
LogInformationee 
(ee 
$stree <
)ee< =
;ee= >
constgg 
stringgg 
sqlgg 
=gg 
$strgo 
;oo 
varqq 
fcqq 
=qq 
awaitqq 
_repositoryqq "
.qq" #
QueryGeoJsonAsyncqq# 4
(qq4 5
sqlqq5 8
,qq8 9
nullqq: >
,qq> ?
ctqq@ B
)qqB C
;qqC D
activityss 
?ss 
.ss 
SetTagss 
(ss 
FeatureCountTagss (
,ss( )
fcss* ,
.ss, -
Countss- 2
)ss2 3
;ss3 4
_loggertt 
.tt 
LogInformationtt 
(tt 
$strtt T
,ttT U
fcttV X
.ttX Y
CountttY ^
)tt^ _
;tt_ `
returnvv 
fcvv 
;vv 
}ww 
}xx 
public~~ 
sealed~~ 
class~~ !
ComplianceDataService~~ )
:~~* +"
IComplianceDataService~~, B
{ 
private
ÄÄ 
static
ÄÄ 
readonly
ÄÄ 
ActivitySource
ÄÄ *
Source
ÄÄ+ 1
=
ÄÄ2 3
new
ÄÄ4 7
(
ÄÄ7 8
$str
ÄÄ8 X
)
ÄÄX Y
;
ÄÄY Z
private
ÇÇ 
readonly
ÇÇ  
IPostGisRepository
ÇÇ '
_repository
ÇÇ( 3
;
ÇÇ3 4
private
ÉÉ 
readonly
ÉÉ 
ILogger
ÉÉ 
<
ÉÉ #
ComplianceDataService
ÉÉ 2
>
ÉÉ2 3
_logger
ÉÉ4 ;
;
ÉÉ; <
public
ÖÖ 
#
ComplianceDataService
ÖÖ  
(
ÖÖ  ! 
IPostGisRepository
ÜÜ 

repository
ÜÜ %
,
ÜÜ% &
ILogger
ÜÜ' .
<
ÜÜ. /#
ComplianceDataService
ÜÜ/ D
>
ÜÜD E
logger
ÜÜF L
)
ÜÜL M
{
áá 
_repository
àà 
=
àà 

repository
àà  
??
àà! #
throw
àà$ )
new
àà* -#
ArgumentNullException
àà. C
(
ààC D
nameof
ààD J
(
ààJ K

repository
ààK U
)
ààU V
)
ààV W
;
ààW X
_logger
ââ 
=
ââ 
logger
ââ 
??
ââ 
throw
ââ !
new
ââ" %#
ArgumentNullException
ââ& ;
(
ââ; <
nameof
ââ< B
(
ââB C
logger
ââC I
)
ââI J
)
ââJ K
;
ââK L
}
ää 
public
çç 

async
çç 
Task
çç 
<
çç 
IReadOnlyList
çç #
<
çç# $
VegetationReading
çç$ 5
>
çç5 6
>
çç6 7(
GetVegetationByBufferAsync
çç8 R
(
ççR S
int
éé 
bufferId
éé 
,
éé 
CancellationToken
éé '
ct
éé( *
)
éé* +
{
èè 
using
êê 
var
êê 
activity
êê 
=
êê 
Source
êê #
.
êê# $
StartActivity
êê$ 1
(
êê1 2
$str
êê2 X
)
êêX Y
;
êêY Z
activity
ëë 
?
ëë 
.
ëë 
SetTag
ëë 
(
ëë 
$str
ëë $
,
ëë$ %
bufferId
ëë& .
)
ëë. /
;
ëë/ 0
if
ìì 

(
ìì 
bufferId
ìì 
<=
ìì 
$num
ìì 
)
ìì 
{
îî 	
throw
ïï 
new
ïï 
ArgumentException
ïï '
(
ïï' (
$"
ññ 
$str
ññ 2
{
ññ2 3
bufferId
ññ3 ;
}
ññ; <
"
ññ< =
,
ññ= >
nameof
ññ? E
(
ññE F
bufferId
ññF N
)
ññN O
)
ññO P
;
ññP Q
}
óó 	
_logger
ôô 
.
ôô 
LogInformation
ôô 
(
ôô 
$str
ôô S
,
ôôS T
bufferId
ôôU ]
)
ôô] ^
;
ôô^ _
const
õõ 
string
õõ 
sql
õõ 
=
õõ 
$str
õ° 
;
°° 
var
££ 
readings
££ 
=
££ 
await
££ 
_repository
££ (
.
££( )

QueryAsync
££) 3
<
££3 4
VegetationReading
££4 E
>
££E F
(
££F G
sql
££G J
,
££J K
new
££L O
{
££P Q
bufferId
££R Z
}
££[ \
,
££\ ]
ct
££^ `
)
££` a
;
££a b
_logger
•• 
.
•• 
LogInformation
•• 
(
•• 
$str
¶¶ Q
,
¶¶Q R
bufferId
ßß 
,
ßß 
readings
ßß 
.
ßß 
Count
ßß $
)
ßß$ %
;
ßß% &
return
©© 
readings
©© 
;
©© 
}
™™ 
public
≠≠ 

async
≠≠ 
Task
≠≠ 
<
≠≠ 
IReadOnlyList
≠≠ #
<
≠≠# $
ComplianceSummary
≠≠$ 5
>
≠≠5 6
>
≠≠6 7
GetSummaryAsync
≠≠8 G
(
≠≠G H
CancellationToken
≠≠H Y
ct
≠≠Z \
)
≠≠\ ]
{
ÆÆ 
using
ØØ 
var
ØØ 
activity
ØØ 
=
ØØ 
Source
ØØ #
.
ØØ# $
StartActivity
ØØ$ 1
(
ØØ1 2
$str
ØØ2 M
)
ØØM N
;
ØØN O
_logger
±± 
.
±± 
LogInformation
±± 
(
±± 
$str
±± M
)
±±M N
;
±±N O
const
≥≥ 
string
≥≥ 
sql
≥≥ 
=
≥≥ 
$str
≥π 
;
ππ 
var
ªª 
	summaries
ªª 
=
ªª 
await
ªª 
_repository
ªª )
.
ªª) *

QueryAsync
ªª* 4
<
ªª4 5
ComplianceSummary
ªª5 F
>
ªªF G
(
ªªG H
sql
ªªH K
,
ªªK L
null
ªªM Q
,
ªªQ R
ct
ªªS U
)
ªªU V
;
ªªV W
_logger
ΩΩ 
.
ΩΩ 
LogInformation
ΩΩ 
(
ΩΩ 
$str
ΩΩ O
,
ΩΩO P
	summaries
ΩΩQ Z
.
ΩΩZ [
Count
ΩΩ[ `
)
ΩΩ` a
;
ΩΩa b
return
øø 
	summaries
øø 
;
øø 
}
¿¿ 
}¡¡ “Z
Y/Volumes/Mac OS Extended 1/riparian-poc/RiparianPoc.Api/Repositories/PostGisRepository.cs
	namespace		 	
RiparianPoc		
 
.		 
Api		 
.		 
Repositories		 &
;		& '
public 
sealed 
class 
PostGisRepository %
:& '
IPostGisRepository( :
{ 
private 
const 
string 
DurationTag $
=% &
$str' 7
;7 8
private 
static 
readonly 
ActivitySource *
Source+ 1
=2 3
new4 7
(7 8
$str8 T
)T U
;U V
private 
static 
readonly !
JsonSerializerOptions 1
GeoJsonOptions2 @
=A B
newC F
(F G
)G H
{ 

Converters 
= 
{ 
new #
GeoJsonConverterFactory 2
(2 3
)3 4
}5 6
} 
; 
private 
readonly 
NpgsqlDataSource %
_db& )
;) *
private 
readonly 
ILogger 
< 
PostGisRepository .
>. /
_logger0 7
;7 8
public 

PostGisRepository 
( 
NpgsqlDataSource -
db. 0
,0 1
ILogger2 9
<9 :
PostGisRepository: K
>K L
loggerM S
)S T
{ 
_db 
= 
db 
?? 
throw 
new !
ArgumentNullException 3
(3 4
nameof4 :
(: ;
db; =
)= >
)> ?
;? @
_logger 
= 
logger 
?? 
throw !
new" %!
ArgumentNullException& ;
(; <
nameof< B
(B C
loggerC I
)I J
)J K
;K L
}   
public## 

async## 
Task## 
<## 
FeatureCollection## '
>##' (
QueryGeoJsonAsync##) :
(##: ;
string$$ 
sql$$ 
,$$ 
object$$ 
?$$ 

parameters$$ &
,$$& '
CancellationToken$$( 9
ct$$: <
)$$< =
{%% 
using&& 
var&& 
activity&& 
=&& 
Source&& #
.&&# $
StartActivity&&$ 1
(&&1 2
$str&&2 H
)&&H I
;&&I J
var'' 
sw'' 
='' 
	Stopwatch'' 
.'' 
StartNew'' #
(''# $
)''$ %
;''% &
try)) 
{** 	
_logger++ 
.++ 
LogDebug++ 
(++ 
$str++ 6
)++6 7
;++7 8
await-- 
using-- 
var-- 
conn--  
=--! "
await--# (
_db--) ,
.--, -
OpenConnectionAsync--- @
(--@ A
ct--A C
)--C D
;--D E
var.. 
rows.. 
=.. 
await.. 
conn.. !
...! "

QueryAsync.." ,
(.., -
new// 
CommandDefinition// %
(//% &
sql//& )
,//) *

parameters//+ 5
,//5 6
cancellationToken//7 H
://H I
ct//J L
)//L M
)//M N
;//N O
var11 
fc11 
=11 
new11 
FeatureCollection11 *
(11* +
)11+ ,
;11, -
foreach22 
(22 
var22 
row22 
in22 
rows22  $
)22$ %
{33 
var44 
dict44 
=44 
(44 
IDictionary44 '
<44' (
string44( .
,44. /
object440 6
?446 7
>447 8
)448 9
row449 <
;44< =
var55 
geojson55 
=55 
(55 
string55 %
)55% &
dict55& *
[55* +
$str55+ 4
]554 5
!555 6
;556 7
dict66 
.66 
Remove66 
(66 
$str66 %
)66% &
;66& '
var77 
geometry77 
=77 
JsonSerializer77 -
.77- .
Deserialize77. 9
<779 :
Geometry77: B
>77B C
(77C D
geojson77D K
,77K L
GeoJsonOptions77M [
)77[ \
;77\ ]
fc88 
.88 
Add88 
(88 
new88 
Feature88 "
(88" #
geometry88# +
,88+ ,
new88- 0
AttributesTable881 @
(88@ A
dict99 
.99 
ToDictionary99 %
(99% &
kv99& (
=>99) +
kv99, .
.99. /
Key99/ 2
,992 3
kv994 6
=>997 9
kv99: <
.99< =
Value99= B
)99B C
)99C D
)99D E
)99E F
;99F G
}:: 
sw<< 
.<< 
Stop<< 
(<< 
)<< 
;<< 
activity== 
?== 
.== 
SetTag== 
(== 
$str== /
,==/ 0
fc==1 3
.==3 4
Count==4 9
)==9 :
;==: ;
activity>> 
?>> 
.>> 
SetTag>> 
(>> 
DurationTag>> (
,>>( )
sw>>* ,
.>>, -
ElapsedMilliseconds>>- @
)>>@ A
;>>A B
_logger?? 
.?? 
LogDebug?? 
(?? 
$str@@ Q
,@@Q R
fcAA 
.AA 
CountAA 
,AA 
swAA 
.AA 
ElapsedMillisecondsAA 0
)AA0 1
;AA1 2
returnCC 
fcCC 
;CC 
}DD 	
catchEE 
(EE 
NpgsqlExceptionEE 
exEE !
)EE! "
{FF 	
swGG 
.GG 
StopGG 
(GG 
)GG 
;GG 
activityHH 
?HH 
.HH 
	SetStatusHH 
(HH  
ActivityStatusCodeHH  2
.HH2 3
ErrorHH3 8
,HH8 9
exHH: <
.HH< =
MessageHH= D
)HHD E
;HHE F
activityII 
?II 
.II 
SetTagII 
(II 
$strII $
,II$ %
trueII& *
)II* +
;II+ ,
activityJJ 
?JJ 
.JJ 
SetTagJJ 
(JJ 
DurationTagJJ (
,JJ( )
swJJ* ,
.JJ, -
ElapsedMillisecondsJJ- @
)JJ@ A
;JJA B
throwKK 
newKK %
InvalidOperationExceptionKK /
(KK/ 0
$"LL 
$strLL 5
{LL5 6
swLL6 8
.LL8 9
ElapsedMillisecondsLL9 L
}LLL M
$strLLM O
"LLO P
,LLP Q
exLLR T
)LLT U
;LLU V
}MM 	
}NN 
publicQQ 

asyncQQ 
TaskQQ 
<QQ 
IReadOnlyListQQ #
<QQ# $
TQQ$ %
>QQ% &
>QQ& '

QueryAsyncQQ( 2
<QQ2 3
TQQ3 4
>QQ4 5
(QQ5 6
stringRR 
sqlRR 
,RR 
objectRR 
?RR 

parametersRR &
,RR& '
CancellationTokenRR( 9
ctRR: <
)RR< =
{SS 
usingTT 
varTT 
activityTT 
=TT 
SourceTT #
.TT# $
StartActivityTT$ 1
(TT1 2
$strTT2 F
)TTF G
;TTG H
activityUU 
?UU 
.UU 
SetTagUU 
(UU 
$strUU )
,UU) *
typeofUU+ 1
(UU1 2
TUU2 3
)UU3 4
.UU4 5
NameUU5 9
)UU9 :
;UU: ;
varVV 
swVV 
=VV 
	StopwatchVV 
.VV 
StartNewVV #
(VV# $
)VV$ %
;VV% &
tryXX 
{YY 	
_loggerZZ 
.ZZ 
LogDebugZZ 
(ZZ 
$strZZ ?
,ZZ? @
typeofZZA G
(ZZG H
TZZH I
)ZZI J
.ZZJ K
NameZZK O
)ZZO P
;ZZP Q
await\\ 
using\\ 
var\\ 
conn\\  
=\\! "
await\\# (
_db\\) ,
.\\, -
OpenConnectionAsync\\- @
(\\@ A
ct\\A C
)\\C D
;\\D E
var]] 
results]] 
=]] 
(]] 
await]]  
conn]]! %
.]]% &

QueryAsync]]& 0
<]]0 1
T]]1 2
>]]2 3
(]]3 4
new^^ 
CommandDefinition^^ %
(^^% &
sql^^& )
,^^) *

parameters^^+ 5
,^^5 6
cancellationToken^^7 H
:^^H I
ct^^J L
)^^L M
)^^M N
)^^N O
.^^O P
AsList^^P V
(^^V W
)^^W X
;^^X Y
sw`` 
.`` 
Stop`` 
(`` 
)`` 
;`` 
activityaa 
?aa 
.aa 
SetTagaa 
(aa 
$straa +
,aa+ ,
resultsaa- 4
.aa4 5
Countaa5 :
)aa: ;
;aa; <
activitybb 
?bb 
.bb 
SetTagbb 
(bb 
DurationTagbb (
,bb( )
swbb* ,
.bb, -
ElapsedMillisecondsbb- @
)bb@ A
;bbA B
_loggercc 
.cc 
LogDebugcc 
(cc 
$strdd D
,ddD E
resultsee 
.ee 
Countee 
,ee 
swee !
.ee! "
ElapsedMillisecondsee" 5
)ee5 6
;ee6 7
returngg 
resultsgg 
;gg 
}hh 	
catchii 
(ii 
NpgsqlExceptionii 
exii !
)ii! "
{jj 	
swkk 
.kk 
Stopkk 
(kk 
)kk 
;kk 
activityll 
?ll 
.ll 
	SetStatusll 
(ll  
ActivityStatusCodell  2
.ll2 3
Errorll3 8
,ll8 9
exll: <
.ll< =
Messagell= D
)llD E
;llE F
activitymm 
?mm 
.mm 
SetTagmm 
(mm 
$strmm $
,mm$ %
truemm& *
)mm* +
;mm+ ,
activitynn 
?nn 
.nn 
SetTagnn 
(nn 
DurationTagnn (
,nn( )
swnn* ,
.nn, -
ElapsedMillisecondsnn- @
)nn@ A
;nnA B
throwoo 
newoo %
InvalidOperationExceptionoo /
(oo/ 0
$"pp 
$strpp "
{pp" #
typeofpp# )
(pp) *
Tpp* +
)pp+ ,
.pp, -
Namepp- 1
}pp1 2
$strpp2 @
{pp@ A
swppA C
.ppC D
ElapsedMillisecondsppD W
}ppW X
$strppX Z
"ppZ [
,pp[ \
expp] _
)pp_ `
;pp` a
}qq 	
}rr 
}ss §
Z/Volumes/Mac OS Extended 1/riparian-poc/RiparianPoc.Api/Repositories/IPostGisRepository.cs
	namespace 	
RiparianPoc
 
. 
Api 
. 
Repositories &
;& '
public 
	interface 
IPostGisRepository #
{		 
Task 
< 	
FeatureCollection	 
> 
QueryGeoJsonAsync -
(- .
string. 4
sql5 8
,8 9
object: @
?@ A

parametersB L
,L M
CancellationTokenN _
ct` b
)b c
;c d
Task 
< 	
IReadOnlyList	 
< 
T 
> 
> 

QueryAsync %
<% &
T& '
>' (
(( )
string) /
sql0 3
,3 4
object5 ;
?; <

parameters= G
,G H
CancellationTokenI Z
ct[ ]
)] ^
;^ _
} ›
R/Volumes/Mac OS Extended 1/riparian-poc/RiparianPoc.Api/Models/ApiErrorResponse.cs
	namespace 	
RiparianPoc
 
. 
Api 
. 
Models  
;  !
public 
sealed 
record 
ApiErrorResponse %
(% &
string 

Error 
, 
string 

CorrelationId 
, 
int 

StatusCode 
, 
string 

?
 
Detail 
= 
null 
) 
; Ü$
B/Volumes/Mac OS Extended 1/riparian-poc/RiparianPoc.Api/Program.cs
Dapper 
. 
DefaultTypeMap 
. %
MatchNamesWithUnderscores /
=0 1
true2 6
;6 7
var

 
builder

 
=

 
WebApplication

 
.

 
CreateBuilder

 *
(

* +
args

+ /
)

/ 0
;

0 1
builder 
. 
AddServiceDefaults 
( 
) 
; 
builder 
. 
AddNpgsqlDataSource 
( 
$str (
)( )
;) *
builder 
. 
Services 
. 
	AddScoped 
< 
IPostGisRepository -
,- .
PostGisRepository/ @
>@ A
(A B
)B C
;C D
builder 
. 
Services 
. 
	AddScoped 
<  
ISpatialQueryService /
,/ 0
SpatialQueryService1 D
>D E
(E F
)F G
;G H
builder 
. 
Services 
. 
	AddScoped 
< "
IComplianceDataService 1
,1 2!
ComplianceDataService3 H
>H I
(I J
)J K
;K L
builder 
. 
Services 
. 
AddOpenTelemetry !
(! "
)" #
. 
WithTracing 
( 
tracing 
=> 
tracing #
. 	
	AddSource	 
( 
$str /
)/ 0
. 	
	AddSource	 
( 
$str 1
)1 2
. 	
	AddSource	 
( 
$str 3
)3 4
)4 5
;5 6
builder 
. 
Services 
. $
ConfigureHttpJsonOptions )
() *
options* 1
=>2 4
{ 
options   
.   
SerializerOptions   
.   

Converters   (
.  ( )
Add  ) ,
(  , -
new  - 0#
GeoJsonConverterFactory  1 H
(  H I
)  I J
)  J K
;  K L
}!! 
)!! 
;!! 
builder## 
.## 
Services## 
.## 

AddOpenApi## 
(## 
)## 
;## 
builder&& 
.&& 
Services&& 
.&& 
AddCors&& 
(&& 
options&&  
=>&&! #
{'' 
options(( 
.(( 
AddDefaultPolicy(( 
((( 
policy(( #
=>(($ &
{)) 
policy** 
.** 
AllowAnyOrigin** 
(** 
)** 
.++ 
AllowAnyMethod++ 
(++ 
)++ 
.,, 
AllowAnyHeader,, 
(,, 
),, 
.-- 
WithExposedHeaders-- !
(--! "
$str--" 4
)--4 5
;--5 6
}.. 
).. 
;.. 
}// 
)// 
;// 
var11 
app11 
=11 	
builder11
 
.11 
Build11 
(11 
)11 
;11 
app33 
.33 
MapDefaultEndpoints33 
(33 
)33 
;33 
if55 
(55 
app55 
.55 
Environment55 
.55 
IsDevelopment55 !
(55! "
)55" #
)55# $
{66 
app77 
.77 

MapOpenApi77 
(77 
)77 
;77 
}88 
app;; 
.;; 
UseMiddleware;; 
<;; !
CorrelationMiddleware;; '
>;;' (
(;;( )
);;) *
;;;* +
app>> 
.>> 
UseMiddleware>> 
<>> '
ExceptionHandlingMiddleware>> -
>>>- .
(>>. /
)>>/ 0
;>>0 1
app@@ 
.@@ 
UseCors@@ 
(@@ 
)@@ 
;@@ 
appAA 
.AA 
UseHttpsRedirectionAA 
(AA 
)AA 
;AA 
appBB 
.BB 
MapGeoDataEndpointsBB 
(BB 
)BB 
;BB 
awaitDD 
appDD 	
.DD	 

RunAsyncDD
 
(DD 
)DD 
;DD ¸?
a/Volumes/Mac OS Extended 1/riparian-poc/RiparianPoc.Api/Middleware/ExceptionHandlingMiddleware.cs
	namespace 	
RiparianPoc
 
. 
Api 
. 

Middleware $
;$ %
public 
sealed 
class '
ExceptionHandlingMiddleware /
{ 
private 
readonly 
RequestDelegate $
_next% *
;* +
private 
readonly 
ILogger 
< '
ExceptionHandlingMiddleware 8
>8 9
_logger: A
;A B
private 
readonly 
IHostEnvironment %
_environment& 2
;2 3
public 
'
ExceptionHandlingMiddleware &
(& '
RequestDelegate 
next 
, 
ILogger 
< '
ExceptionHandlingMiddleware +
>+ ,
logger- 3
,3 4
IHostEnvironment 
environment $
)$ %
{ 
_next 
= 
next 
?? 
throw 
new !!
ArgumentNullException" 7
(7 8
nameof8 >
(> ?
next? C
)C D
)D E
;E F
_logger 
= 
logger 
?? 
throw !
new" %!
ArgumentNullException& ;
(; <
nameof< B
(B C
loggerC I
)I J
)J K
;K L
_environment 
= 
environment "
??# %
throw& +
new, /!
ArgumentNullException0 E
(E F
nameofF L
(L M
environmentM X
)X Y
)Y Z
;Z [
} 
public   

async   
Task   
InvokeAsync   !
(  ! "
HttpContext  " -
context  . 5
)  5 6
{!! 
try"" 
{## 	
await$$ 
_next$$ 
($$ 
context$$ 
)$$  
;$$  !
}%% 	
catch&& 
(&& &
OperationCanceledException&& )
ex&&* ,
)&&, -
when&&. 2
(&&3 4
context&&4 ;
.&&; <
RequestAborted&&< J
.&&J K#
IsCancellationRequested&&K b
)&&b c
{'' 	
_logger)) 
.)) 
LogDebug)) 
()) 
ex)) 
,))  
$str))! O
,))O P
context** 
.** 
Request** 
.**  
Method**  &
,**& '
context**( /
.**/ 0
Request**0 7
.**7 8
Path**8 <
)**< =
;**= >
}++ 	
catch,, 
(,, 
	Exception,, 
ex,, 
),, 
{-- 	
await..  
HandleExceptionAsync.. &
(..& '
context..' .
,... /
ex..0 2
)..2 3
;..3 4
}// 	
}00 
private22 
async22 
Task22  
HandleExceptionAsync22 +
(22+ ,
HttpContext22, 7
context228 ?
,22? @
	Exception22A J
	exception22K T
)22T U
{33 
var77 
(77 

statusCode77 
,77 
message77  
)77  !
=77" #
	exception77$ -
switch77. 4
{88 	
NpgsqlException99 
=>99 
(99  
StatusCodes99  +
.99+ ,'
Status503ServiceUnavailable99, G
,99G H
$str::  B
)::B C
,::C D
_;; 
when;; 
	exception;; 
.;; 
InnerException;; +
is;;, .
NpgsqlException;;/ >
=><< 
(<< 
StatusCodes<< 
.<<  '
Status503ServiceUnavailable<<  ;
,<<; <
$str== 6
)==6 7
,==7 8
ArgumentException>> 
ex>>  
=>>>! #
(>>$ %
StatusCodes>>% 0
.>>0 1
Status400BadRequest>>1 D
,>>D E
ex??% '
.??' (
Message??( /
)??/ 0
,??0 1 
KeyNotFoundException@@  
ex@@! #
=>@@$ &
(@@' (
StatusCodes@@( 3
.@@3 4
Status404NotFound@@4 E
,@@E F
exAA( *
.AA* +
MessageAA+ 2
)AA2 3
,AA3 4&
OperationCanceledExceptionBB &
=>BB' )
(BB* +
StatusCodesBB+ 6
.BB6 7#
Status504GatewayTimeoutBB7 N
,BBN O
$strCC+ >
)CC> ?
,CC? @
_DD 
=>DD 
(DD 
StatusCodesDD 
.DD (
Status500InternalServerErrorDD :
,DD: ;
$strEE 0
)EE0 1
,EE1 2
}FF 	
;FF	 

varHH 
correlationIdHH 
=HH 
ActivityHH $
.HH$ %
CurrentHH% ,
?HH, -
.HH- .
TraceIdHH. 5
.HH5 6
ToStringHH6 >
(HH> ?
)HH? @
??II 
contextII &
.II& '
ResponseII' /
.II/ 0
HeadersII0 7
[II7 8
$strII8 J
]IIJ K
.IIK L
FirstOrDefaultIIL Z
(IIZ [
)II[ \
??JJ 
$strJJ (
;JJ( )
ifLL 

(LL 

statusCodeLL 
>=LL 
$numLL 
)LL 
{MM 	
_loggerNN 
.NN 
LogErrorNN 
(NN 
	exceptionNN &
,NN& '
$strOO O
,OOO P
	exceptionPP 
.PP 
MessagePP !
,PP! "

statusCodePP# -
)PP- .
;PP. /
}QQ 	
elseRR 
{SS 	
_loggerTT 
.TT 

LogWarningTT 
(TT 
	exceptionTT (
,TT( )
$strUU I
,UUI J
	exceptionVV 
.VV 
MessageVV !
,VV! "

statusCodeVV# -
)VV- .
;VV. /
}WW 	
ActivityYY 
.YY 
CurrentYY 
?YY 
.YY 
SetTagYY  
(YY  !
$strYY! (
,YY( )
trueYY* .
)YY. /
;YY/ 0
ActivityZZ 
.ZZ 
CurrentZZ 
?ZZ 
.ZZ 
SetTagZZ  
(ZZ  !
$strZZ! -
,ZZ- .
	exceptionZZ/ 8
.ZZ8 9
GetTypeZZ9 @
(ZZ@ A
)ZZA B
.ZZB C
NameZZC G
)ZZG H
;ZZH I
Activity[[ 
.[[ 
Current[[ 
?[[ 
.[[ 
	SetStatus[[ #
([[# $
ActivityStatusCode[[$ 6
.[[6 7
Error[[7 <
,[[< =
	exception[[> G
.[[G H
Message[[H O
)[[O P
;[[P Q
var]] 
detail]] 
=]] 
_environment]] !
.]]! "
IsDevelopment]]" /
(]]/ 0
)]]0 1
?]]2 3
	exception]]4 =
.]]= >
ToString]]> F
(]]F G
)]]G H
:]]I J
null]]K O
;]]O P
var^^ 
errorResponse^^ 
=^^ 
new^^ 
ApiErrorResponse^^  0
(^^0 1
message^^1 8
,^^8 9
correlationId^^: G
,^^G H

statusCode^^I S
,^^S T
detail^^U [
)^^[ \
;^^\ ]
context`` 
.`` 
Response`` 
.`` 

StatusCode`` #
=``$ %

statusCode``& 0
;``0 1
contextaa 
.aa 
Responseaa 
.aa 
ContentTypeaa $
=aa% &
$straa' 9
;aa9 :
awaitbb 
contextbb 
.bb 
Responsebb 
.bb 
WriteAsJsonAsyncbb /
(bb/ 0
errorResponsebb0 =
)bb= >
;bb> ?
}cc 
}dd ß*
[/Volumes/Mac OS Extended 1/riparian-poc/RiparianPoc.Api/Middleware/CorrelationMiddleware.cs
	namespace 	
RiparianPoc
 
. 
Api 
. 

Middleware $
;$ %
public

 
sealed

 
class

 !
CorrelationMiddleware

 )
{ 
private 
const 
string 
CorrelationIdHeader ,
=- .
$str/ A
;A B
private 
const 
string 
SessionIdHeader (
=) *
$str+ 9
;9 :
private 
readonly 
RequestDelegate $
_next% *
;* +
private 
readonly 
ILogger 
< !
CorrelationMiddleware 2
>2 3
_logger4 ;
;; <
public 
!
CorrelationMiddleware  
(  !
RequestDelegate! 0
next1 5
,5 6
ILogger7 >
<> ?!
CorrelationMiddleware? T
>T U
loggerV \
)\ ]
{ 
_next 
= 
next 
?? 
throw 
new !!
ArgumentNullException" 7
(7 8
nameof8 >
(> ?
next? C
)C D
)D E
;E F
_logger 
= 
logger 
?? 
throw !
new" %!
ArgumentNullException& ;
(; <
nameof< B
(B C
loggerC I
)I J
)J K
;K L
} 
public 

async 
Task 
InvokeAsync !
(! "
HttpContext" -
context. 5
)5 6
{ 
var 
correlationId 
= 
context #
.# $
Request$ +
.+ ,
Headers, 3
[3 4
CorrelationIdHeader4 G
]G H
.H I
FirstOrDefaultI W
(W X
)X Y
?? 
Activity '
.' (
Current( /
?/ 0
.0 1
TraceId1 8
.8 9
ToString9 A
(A B
)B C
??   
Guid   #
.  # $
NewGuid  $ +
(  + ,
)  , -
.  - .
ToString  . 6
(  6 7
$str  7 :
)  : ;
;  ; <
var"" 
	sessionId"" 
="" 
context"" 
.""  
Request""  '
.""' (
Headers""( /
[""/ 0
SessionIdHeader""0 ?
]""? @
.""@ A
FirstOrDefault""A O
(""O P
)""P Q
??""R T
$str""U ^
;""^ _
var## 
clientIp## 
=## 
context## 
.## 

Connection## )
.##) *
RemoteIpAddress##* 9
?##9 :
.##: ;
ToString##; C
(##C D
)##D E
??##F H
$str##I R
;##R S
var%% 
activity%% 
=%% 
Activity%% 
.%%  
Current%%  '
;%%' (
activity&& 
?&& 
.&& 
SetTag&& 
(&& 
$str&& )
,&&) *
correlationId&&+ 8
)&&8 9
;&&9 :
activity'' 
?'' 
.'' 
SetTag'' 
('' 
$str'' %
,''% &
	sessionId''' 0
)''0 1
;''1 2
activity(( 
?(( 
.(( 
SetTag(( 
((( 
$str(( $
,(($ %
clientIp((& .
)((. /
;((/ 0
context** 
.** 
Response** 
.** 

OnStarting** #
(**# $
(**$ %
)**% &
=>**' )
{++ 	
context,, 
.,, 
Response,, 
.,, 
Headers,, $
[,,$ %
CorrelationIdHeader,,% 8
],,8 9
=,,: ;
correlationId,,< I
;,,I J
return-- 
Task-- 
.-- 
CompletedTask-- %
;--% &
}.. 	
)..	 

;..
 
using00 
(00 
_logger00 
.00 

BeginScope00 !
(00! "
new00" %

Dictionary00& 0
<000 1
string001 7
,007 8
object009 ?
>00? @
{11 	
[22 
$str22 
]22 
=22 
correlationId22  -
,22- .
[33 
$str33 
]33 
=33 
	sessionId33 %
,33% &
[44 
$str44 
]44 
=44 
clientIp44 #
,44# $
}55 	
)55	 

)55
 
{66 	
_logger77 
.77 
LogDebug77 
(77 
$str88 2
,882 3
context99 
.99 
Request99 
.99  
Method99  &
,99& '
context:: 
.:: 
Request:: 
.::  
Path::  $
)::$ %
;::% &
await<< 
_next<< 
(<< 
context<< 
)<<  
;<<  !
}== 	
}>> 
}?? Í@
U/Volumes/Mac OS Extended 1/riparian-poc/RiparianPoc.Api/Endpoints/GeoDataEndpoints.cs
	namespace 	
RiparianPoc
 
. 
Api 
. 
	Endpoints #
;# $
public 
static 
class 
GeoDataEndpoints $
{		 
public 

static !
IEndpointRouteBuilder '
MapGeoDataEndpoints( ;
(; <
this< @!
IEndpointRouteBuilderA V
appW Z
)Z [
{ 
var 
api 
= 
app 
. 
MapGroup 
( 
$str %
)% &
;& '
api 
. 
MapGet 
( 
$str 
, 

GetStreams )
)) *
.* +
WithName+ 3
(3 4
$str4 @
)@ A
;A B
api 
. 
MapGet 
( 
$str 
, 

GetBuffers )
)) *
.* +
WithName+ 3
(3 4
$str4 @
)@ A
;A B
api 
. 
MapGet 
( 
$str 
, 

GetParcels )
)) *
.* +
WithName+ 3
(3 4
$str4 @
)@ A
;A B
api 
. 
MapGet 
( 
$str !
,! "
GetFocusAreas# 0
)0 1
.1 2
WithName2 :
(: ;
$str; J
)J K
;K L
api 
. 
MapGet 
( 
$str 7
,7 8!
GetVegetationByBuffer9 N
)N O
. 
WithName 
( 
$str -
)- .
;. /
api 
. 
MapGet 
( 
$str 
, 

GetSummary )
)) *
.* +
WithName+ 3
(3 4
$str4 @
)@ A
;A B
return 
app 
; 
} 
private 
static 
async 
Task 
< 
IResult %
>% &

GetStreams' 1
(1 2 
ISpatialQueryService   
spatialService   +
,  + ,
CancellationToken  - >
ct  ? A
)  A B
{!! 
var"" 
fc"" 
="" 
await"" 
spatialService"" %
.""% &
GetStreamsAsync""& 5
(""5 6
ct""6 8
)""8 9
;""9 :
return## 
TypedResults## 
.## 
Ok## 
(## 
fc## !
)##! "
;##" #
}$$ 
private)) 
static)) 
async)) 
Task)) 
<)) 
IResult)) %
>))% &

GetBuffers))' 1
())1 2 
ISpatialQueryService** 
spatialService** +
,**+ ,
CancellationToken**- >
ct**? A
)**A B
{++ 
var,, 
fc,, 
=,, 
await,, 
spatialService,, %
.,,% &
GetBuffersAsync,,& 5
(,,5 6
ct,,6 8
),,8 9
;,,9 :
return-- 
TypedResults-- 
.-- 
Ok-- 
(-- 
fc-- !
)--! "
;--" #
}.. 
private33 
static33 
async33 
Task33 
<33 
IResult33 %
>33% &

GetParcels33' 1
(331 2 
ISpatialQueryService44 
spatialService44 +
,44+ ,
CancellationToken44- >
ct44? A
)44A B
{55 
var66 
fc66 
=66 
await66 
spatialService66 %
.66% &
GetParcelsAsync66& 5
(665 6
ct666 8
)668 9
;669 :
return77 
TypedResults77 
.77 
Ok77 
(77 
fc77 !
)77! "
;77" #
}88 
private== 
static== 
async== 
Task== 
<== 
IResult== %
>==% &
GetFocusAreas==' 4
(==4 5 
ISpatialQueryService>> 
spatialService>> +
,>>+ ,
CancellationToken>>- >
ct>>? A
)>>A B
{?? 
var@@ 
fc@@ 
=@@ 
await@@ 
spatialService@@ %
.@@% &
GetFocusAreasAsync@@& 8
(@@8 9
ct@@9 ;
)@@; <
;@@< =
returnAA 
TypedResultsAA 
.AA 
OkAA 
(AA 
fcAA !
)AA! "
;AA" #
}BB 
privateGG 
staticGG 
asyncGG 
TaskGG 
<GG 
IResultGG %
>GG% &!
GetVegetationByBufferGG' <
(GG< =
intHH 
bufferIdHH 
,HH "
IComplianceDataServiceHH ,
complianceServiceHH- >
,HH> ?
CancellationTokenHH@ Q
ctHHR T
)HHT U
{II 
varJJ 
readingsJJ 
=JJ 
awaitJJ 
complianceServiceJJ .
.JJ. /&
GetVegetationByBufferAsyncJJ/ I
(JJI J
bufferIdJJJ R
,JJR S
ctJJT V
)JJV W
;JJW X
returnKK 
TypedResultsKK 
.KK 
OkKK 
(KK 
readingsKK '
)KK' (
;KK( )
}LL 
privateQQ 
staticQQ 
asyncQQ 
TaskQQ 
<QQ 
IResultQQ %
>QQ% &

GetSummaryQQ' 1
(QQ1 2"
IComplianceDataServiceRR 
complianceServiceRR 0
,RR0 1
CancellationTokenRR2 C
ctRRD F
)RRF G
{SS 
varTT 
	summariesTT 
=TT 
awaitTT 
complianceServiceTT /
.TT/ 0
GetSummaryAsyncTT0 ?
(TT? @
ctTT@ B
)TTB C
;TTC D
returnUU 
TypedResultsUU 
.UU 
OkUU 
(UU 
	summariesUU (
)UU( )
;UU) *
}VV 
}WW 
public\\ 
sealed\\ 
record\\ 
VegetationReading\\ &
(\\& '
int]] 
Id]] 

,]]
 
int^^ 
BufferId^^ 
,^^ 
DateOnly__ 
AcquisitionDate__ 
,__ 
decimal`` 
?`` 
MeanNdvi`` 
,`` 
decimalaa 
?aa 
MinNdviaa 
,aa 
decimalbb 
?bb 
MaxNdvibb 
,bb 
stringcc 

HealthCategorycc 
,cc 
stringdd 

SeasonContextdd 
,dd 
stringee 

?ee
 
	Satelliteee 
,ee 
DateTimeOffsetff 
ProcessedAtff 
)ff 
;ff  
publickk 
sealedkk 
recordkk 
ComplianceSummarykk &
(kk& '
intll 
Idll 

,ll
 
intmm 
WatershedIdmm 
,mm 
stringnn 

Huc8nn 
,nn 
decimaloo 
?oo 
TotalStreamLengthMoo 
,oo  
decimalpp 
?pp 
TotalBufferAreaSqMpp 
,pp  
intqq 
TotalParcelsqq 
,qq 
intrr 
CompliantParcelsrr 
,rr 
intss 
FocusAreaParcelsss 
,ss 
decimaltt 
?tt 
CompliancePcttt 
,tt 
decimaluu 
?uu 
AvgNdviuu 
,uu 
decimalvv 
?vv 
HealthyBufferPctvv 
,vv 
decimalww 
?ww 
DegradedBufferPctww 
,ww 
decimalxx 
?xx 
BareBufferPctxx 
,xx 
DateTimeOffsetyy 
	CreatedAtyy 
)yy 
;yy 