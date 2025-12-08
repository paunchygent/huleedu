1. Varför – syfte och inriktning

Mitt arbete som AI-ambassadör har utgått från en annan grundpremiss än den som präglar mycket av samtalet om AI i skolan. Jag har valt att fokusera på ett konkret problem – bristande likvärdighet i uppsatsbedömning – och bygga ett system som adresserar det, snarare än att sprida tips om promptar eller assistenter.

Skälet är enkelt: att dela promptar och skapa assistenter är användbart men begränsat då de saknar automatiseringen skalfördelar. Enskilda promptar kommer helt enkelt inte att lösa de strukturella flaskhalsar som faktiskt kostar oss tid och likvärdighet. Bedömning av elevtexter är en sådan flaskhals. Enhetlig forskning och beprövad erfarenhet visar att lärare bedömer olika strängt. Innan vi inom ramen för mitt nuvarande projekt inledde arbetet med sambedömning och kalibrering skiljde det i mitt ämneslag upp till fem betygssteg mellan de hårdaste och mest generösa bedömare på en och samma (svårbedömda) uppsats och i snitt drygt två betygssteg för samtliga uppsatser.

Det är ett likvärdighetsproblem. Det är också ett problem som går att lösa med rätt metod och rätt verktyg.

Genom att kombinera komparativ bedömning med AI-stödd rangordning har jag velat visa att det finns en väg från "lek" till "normalisering" som inte handlar om att alla ska bli entusiaster, utan om att vi bygger något som faktiskt förändrar arbetet.

2. Hur – genomförande och lärdomar

Bedömningssystemet är en del av ett större projekt som jag har arbetat med sedan i våras: en backend med läraren i centrum, där olika tjänster samverkar kring administration, texthantering och bedömning. CJ Assessment – den komparativa bedömningstjänsten – är den mest välutvecklade av dessa.

Under hösten har jag validerat systemet mot engelska uppsatser. Jag har valt engelska eftersom moderna språkmodeller har en naturlig fördel i det språket – fler träningsexempel och högre känslighet för nyanser.

Metoden bygger på Comparative Judgment (CJ), en vetenskapligt välbeforskad och beprövad princip som visar att parvisa jämförelser är enklare att utföra och ger mer samstämmiga bedömningar än traditionella absoluta bedömningar. Istället för att hålla hela betygsskalan i huvudet behöver man med CJ bara avgöra vilken av två uppsatser som är den bättre. En statistisk modell räknar sedan ut en ranking baserad på utfallen. För att koppla rankingen till betyg använder systemet ankaruppsatser – elevtexter med kända, stabila betyg – och dessas position i rankingen för att räkna ut sannolikheter för varje uppsats betyg. 

Jag hari dagarna äntligen kommit så lång att jag har kunnat validera systemet mot en uppsättning på tolv ankaruppsatser som ingår i det nationella proven i Engelska 5. I två separata körningar placerade modellen samtliga uppsatser i exakt den ordning som NAFS expertpanel fastställt. Inga inversioner över betygsgränserna.Ankaruppsatserna tillhör även det prov vars uppsatser ämneslaget använde vid inledande bedömningstillfälle. 

Arbetet har också skett i samverkan med kollegorna i kämneslaget för engelska. Jag har medvetet börjat med den mänskliga delen av metoden – komparativ bedömning utan AI – för att sänka trösklarna innan AI-komponenten introduceras. Ett huvudskäl är att jag menar att man som lärare måste ges tid till att bygga upp tillit till ett för många helt obegripligt system innan man vågar släppa in AI som ett verktyg för ens centrala arbetsuppgifter.

3. Utmaningar – hinder och behov av stöd

Det främsta hindret är därför inte heller tekniskt utan organisatoriskt. För att systemet ska fungera i skarpt läge behövs fler ankaruppsatser – elevtexter där ämneslaget är överens om betyget. De kan bara tas fram genom gemensamma bedömningar, och de bedömningarna kräver att alla deltar ungefär lika mycket. Det går inte att lösa genom att några eldsjälar jobbar extra på egen tid.

Ordinarie konferenstid räcker inte heller till. Konferenserna är för få och för korta i förhållande till den tid som krävs, och mycket av tiden går åt till återkommande administrativa punkter.

Det jag behöver från ledningen är avsatt ämneslagstid för gemensamma bedömningar snarare än pengar till programvara eller information om fler AI-tjänster.

Jag delar också den frustration som andra ambassadörer lyft: att träffarna har varit informationsstyrda med lite utrymme för professionsstyrd dialog kring våra faktiska behov. Vår grupp skapades just för att skolans behov och möjligheter skiljer sig från förvaltningens. Om vi vill komma framåt måste vi befästa den insikten snarare än att låta den förvandlas till tunn fernissa. Ge oss mer tid till att verkligen förstå våra gemensamma behov och hur vi tillsammans kan hitta sätt att möta dem. Det är ett förtroende jag tror att ni vet att vi är kloka nog att hantera ansvarsfullt.

4. Vad är nästa steg – förslag och riktning framåt

Planen är att köra ett skarpt betatest vid vårens nationella prov. För att verkligen testa modellen i skarpt läge och se vad för problem som uppstår i praktiken, behöver ämneslaget ta fram kompletterande ankaruppsatser genom gemensamma bedömningar under vårterminen. Dels för att göra betygsprojiceringen mer robust, dels för att skapa förståelse och förtroende för hur systemet fungerar.

Jag har också kontakt med NAFS och universitetet för att få tillgång till fler validerade ankaruppsatser och för att höra av mig till andra som är intresserade av att utveckla liknande verktyg. Tidsplanen är att systemet ska klara ett riktigt betatest vid vårens nationella prov och prestera tillräckligt bra för att kunna användas som ett pålitligt sambedömningsverktyg.

Mitt arbete kan bidra till ledningens underlag genom att visa hur AI-utveckling kan se ut när den utgår från ett definierat problem och vågar närma sig lösningar systematiskt och med långsiktighet. Det handlar om att identifiera vilka flöden vår arbetstid tar i verkligheten och låta den insikten vägleda oss i förändringsarbetet. Hela poängen med AI-assisterad utveckling är att ta vara på verktygens förmåga att göra skräddarsydda lösningar ekonomiskt försvarbara.
