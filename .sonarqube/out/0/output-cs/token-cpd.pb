Þ:
Q/Volumes/Mac OS Extended 1/riparian-poc/RiparianPoc.ServiceDefaults/Extensions.cs
	namespace 	
	Microsoft
 
. 

Extensions 
. 
Hosting &
;& '
public 
static 
class 

Extensions 
{ 
private 
const 
string 
HealthEndpointPath +
=, -
$str. 7
;7 8
private 
const 
string !
AlivenessEndpointPath .
=/ 0
$str1 9
;9 :
public 

static 
TBuilder 
AddServiceDefaults -
<- .
TBuilder. 6
>6 7
(7 8
this8 <
TBuilder= E
builderF M
)M N
whereO T
TBuilderU ]
:^ _#
IHostApplicationBuilder` w
{ 
builder 
. "
ConfigureOpenTelemetry &
(& '
)' (
;( )
builder 
. "
AddDefaultHealthChecks &
(& '
)' (
;( )
builder 
. 
Services 
. 
AddServiceDiscovery ,
(, -
)- .
;. /
builder 
. 
Services 
. '
ConfigureHttpClientDefaults 4
(4 5
http5 9
=>: <
{ 	
http   
.   (
AddStandardResilienceHandler   -
(  - .
)  . /
;  / 0
http## 
.## 
AddServiceDiscovery## $
(##$ %
)##% &
;##& '
}$$ 	
)$$	 

;$$
 
return,, 
builder,, 
;,, 
}-- 
public// 

static// 
TBuilder// "
ConfigureOpenTelemetry// 1
<//1 2
TBuilder//2 :
>//: ;
(//; <
this//< @
TBuilder//A I
builder//J Q
)//Q R
where//S X
TBuilder//Y a
://b c#
IHostApplicationBuilder//d {
{00 
builder11 
.11 
Logging11 
.11 
AddOpenTelemetry11 (
(11( )
logging11) 0
=>111 3
{22 	
logging33 
.33 #
IncludeFormattedMessage33 +
=33, -
true33. 2
;332 3
logging44 
.44 
IncludeScopes44 !
=44" #
true44$ (
;44( )
}55 	
)55	 

;55
 
builder77 
.77 
Services77 
.77 
AddOpenTelemetry77 )
(77) *
)77* +
.88 
WithMetrics88 
(88 
metrics88  
=>88! #
{99 
metrics:: 
.:: (
AddAspNetCoreInstrumentation:: 4
(::4 5
)::5 6
.;; (
AddHttpClientInstrumentation;; 1
(;;1 2
);;2 3
.<< %
AddRuntimeInstrumentation<< .
(<<. /
)<</ 0
;<<0 1
}== 
)== 
.>> 
WithTracing>> 
(>> 
tracing>>  
=>>>! #
{?? 
tracing@@ 
.@@ 
	AddSource@@ !
(@@! "
builder@@" )
.@@) *
Environment@@* 5
.@@5 6
ApplicationName@@6 E
)@@E F
.AA (
AddAspNetCoreInstrumentationAA 1
(AA1 2
tracingAA2 9
=>AA: <
tracingCC 
.CC  
FilterCC  &
=CC' (
contextCC) 0
=>CC1 3
!DD 
contextDD $
.DD$ %
RequestDD% ,
.DD, -
PathDD- 1
.DD1 2
StartsWithSegmentsDD2 D
(DDD E
HealthEndpointPathDDE W
)DDW X
&&EE 
!EE  
contextEE  '
.EE' (
RequestEE( /
.EE/ 0
PathEE0 4
.EE4 5
StartsWithSegmentsEE5 G
(EEG H!
AlivenessEndpointPathEEH ]
)EE] ^
)FF 
.II (
AddHttpClientInstrumentationII 1
(II1 2
)II2 3
;II3 4
}JJ 
)JJ 
;JJ 
builderLL 
.LL %
AddOpenTelemetryExportersLL )
(LL) *
)LL* +
;LL+ ,
returnNN 
builderNN 
;NN 
}OO 
privateQQ 
staticQQ 
TBuilderQQ %
AddOpenTelemetryExportersQQ 5
<QQ5 6
TBuilderQQ6 >
>QQ> ?
(QQ? @
thisQQ@ D
TBuilderQQE M
builderQQN U
)QQU V
whereQQW \
TBuilderQQ] e
:QQf g#
IHostApplicationBuilderQQh 
{RR 
varSS 
useOtlpExporterSS 
=SS 
!SS 
stringSS %
.SS% &
IsNullOrWhiteSpaceSS& 8
(SS8 9
builderSS9 @
.SS@ A
ConfigurationSSA N
[SSN O
$strSSO l
]SSl m
)SSm n
;SSn o
ifUU 

(UU 
useOtlpExporterUU 
)UU 
{VV 	
builderWW 
.WW 
ServicesWW 
.WW 
AddOpenTelemetryWW -
(WW- .
)WW. /
.WW/ 0
UseOtlpExporterWW0 ?
(WW? @
)WW@ A
;WWA B
}XX 	
returnaa 
builderaa 
;aa 
}bb 
publicdd 

staticdd 
TBuilderdd "
AddDefaultHealthChecksdd 1
<dd1 2
TBuilderdd2 :
>dd: ;
(dd; <
thisdd< @
TBuilderddA I
builderddJ Q
)ddQ R
whereddS X
TBuilderddY a
:ddb c#
IHostApplicationBuilderddd {
{ee 
builderff 
.ff 
Servicesff 
.ff 
AddHealthChecksff (
(ff( )
)ff) *
.hh 
AddCheckhh 
(hh 
$strhh 
,hh 
(hh 
)hh  
=>hh! #
HealthCheckResulthh$ 5
.hh5 6
Healthyhh6 =
(hh= >
)hh> ?
,hh? @
[hhA B
$strhhB H
]hhH I
)hhI J
;hhJ K
returnjj 
builderjj 
;jj 
}kk 
publicmm 

staticmm 
WebApplicationmm  
MapDefaultEndpointsmm! 4
(mm4 5
thismm5 9
WebApplicationmm: H
appmmI L
)mmL M
{nn 
ifqq 

(qq 
appqq 
.qq 
Environmentqq 
.qq 
IsDevelopmentqq )
(qq) *
)qq* +
)qq+ ,
{rr 	
apptt 
.tt 
MapHealthCheckstt 
(tt  
HealthEndpointPathtt  2
)tt2 3
;tt3 4
appww 
.ww 
MapHealthChecksww 
(ww  !
AlivenessEndpointPathww  5
,ww5 6
newww7 :
HealthCheckOptionsww; M
{xx 
	Predicateyy 
=yy 
ryy 
=>yy  
ryy! "
.yy" #
Tagsyy# '
.yy' (
Containsyy( 0
(yy0 1
$stryy1 7
)yy7 8
}zz 
)zz 
;zz 
}{{ 	
return}} 
app}} 
;}} 
}~~ 
} 