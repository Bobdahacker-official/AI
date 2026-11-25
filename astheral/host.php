<?php
declare(strict_types=1);

// This file also provides the deployment functions used by the chat endpoint.
const HOST_CDN = 'https://unpkg.com/php-wasm@0.2.0/';
const HOST_CDN_FALLBACK = 'https://cdn.jsdelivr.net/npm/php-wasm@0.2.0/';
const HOST_FILE_LIMIT = 786432;
const HOST_SITE_LIMIT = 3145728;
const HOST_ACCOUNT_LIMIT = 12582912;
const HOST_TOTAL_LIMIT = 50331648;

function host_init(): void {
    static $ready = false;
    if ($ready) return;
    global $db;
    $db->exec("CREATE TABLE IF NOT EXISTS hosted_sites(
      slug TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      title TEXT NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL, size INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS hosted_files(
      slug TEXT NOT NULL REFERENCES hosted_sites(slug) ON DELETE CASCADE, path TEXT NOT NULL,
      mime TEXT NOT NULL, bytes BLOB NOT NULL, PRIMARY KEY(slug,path));
      CREATE TABLE IF NOT EXISTS hosted_views(
      slug TEXT NOT NULL REFERENCES hosted_sites(slug) ON DELETE CASCADE, day TEXT NOT NULL,
      views INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(slug,day));
      CREATE TABLE IF NOT EXISTS hosted_events(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, created INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS hosted_events_user ON hosted_events(user_id,created);
      CREATE INDEX IF NOT EXISTS hosted_sites_user ON hosted_sites(user_id);");
    $ready = true;
}
function host_require(bool $ok, string $message, int $status = 400): void {
    if (!$ok) throw new RuntimeException($message, $status);
}
function host_slug(string $slug): string {
    $slug = strtolower(trim($slug));
    host_require((bool)preg_match('/^[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?$/D', $slug), 'Use 1–48 letters, numbers and hyphens for the site address.');
    host_require(!in_array($slug,['data','host','index','admin','api','www','cgi-bin','assets','astheral'],true) && !is_dir(__DIR__.'/'.$slug) && !is_file(__DIR__.'/'.$slug), 'That address is reserved.');
    return $slug;
}
function host_path(string $path): string {
    host_require(strlen($path) <= 180 && (bool)preg_match('~^[a-zA-Z0-9_-][a-zA-Z0-9_.-]*(?:/[a-zA-Z0-9_-][a-zA-Z0-9_.-]*){0,8}$~D',$path), 'Invalid file path: '.substr($path,0,120));
    return $path;
}
function host_mime(string $path): string {
    $mimes = [
      'html'=>'text/html; charset=utf-8','htm'=>'text/html; charset=utf-8','php'=>'application/x-astheral-php',
      'css'=>'text/css; charset=utf-8','js'=>'text/javascript; charset=utf-8','mjs'=>'text/javascript; charset=utf-8',
      'txt'=>'text/plain; charset=utf-8','md'=>'text/plain; charset=utf-8','json'=>'application/json','webmanifest'=>'application/manifest+json',
      'svg'=>'image/svg+xml','jpg'=>'image/jpeg','jpeg'=>'image/jpeg','png'=>'image/png','gif'=>'image/gif','webp'=>'image/webp','avif'=>'image/avif','ico'=>'image/x-icon',
      'woff'=>'font/woff','woff2'=>'font/woff2','ttf'=>'font/ttf','mp3'=>'audio/mpeg','ogg'=>'audio/ogg','mp4'=>'video/mp4','webm'=>'video/webm','pdf'=>'application/pdf'
    ];
    $type=$mimes[strtolower(pathinfo($path,PATHINFO_EXTENSION))]??null;
    host_require($type!==null,'Unsupported file type: '.$path);
    return $type;
}
function host_deploy(int $uid, string $slug, string $title, array $input, bool $replace=false): array {
    host_init();
    $slug=host_slug($slug);
    host_require($uid>0,'Sign in first.',401);
    host_require(count($input)>0 && count($input)<=60,'Upload between 1 and 60 files.');
    $files=[]; $size=0;
    foreach($input as $name=>$entry){
        $path=host_path((string)$name); $mime=host_mime($path);
        if(is_string($entry)) $bytes=$entry;
        elseif(is_array($entry) && is_string($entry['base64']??null)){
            host_require(strlen($entry['base64'])<=1048576,'File too large: '.$path,413);
            $bytes=base64_decode($entry['base64'],true);
        }else throw new RuntimeException('Invalid content for '.$path,400);
        host_require(is_string($bytes)&&strlen($bytes)<=HOST_FILE_LIMIT,'File too large: '.$path,413);
        $size+=strlen($bytes); $files[$path]=[$mime,$bytes];
    }
    host_require(isset($files['index.html'])||isset($files['index.php']),'Add index.html or index.php at the project root.');
    host_require($size<=HOST_SITE_LIMIT,'A site can use up to 3 MiB.',413);
    $title=mb_substr(trim($title),0,90)?:$slug;
    global $db;
    $db->exec('BEGIN IMMEDIATE');
    try {
        $existing=q('SELECT user_id,size,created FROM hosted_sites WHERE slug=?',[$slug])->fetch();
        host_require(!$existing||(int)$existing['user_id']===$uid,'This site address is taken.',409);
        host_require(!$existing||$replace,'This site already exists. Choose Update to replace its files.',409);
        $recent=(int)q('SELECT COUNT(*) FROM hosted_events WHERE user_id=? AND created>?',[$uid,time()-600])->fetchColumn();
        host_require($recent<10,'Publish limit reached. Try again in ten minutes.',429);
        $count=(int)q('SELECT COUNT(*) FROM hosted_sites WHERE user_id=?',[$uid])->fetchColumn();
        host_require($existing||$count<12,'An account can publish up to 12 sites.',429);
        $old=(int)($existing['size']??0);
        $used=(int)q('SELECT COALESCE(SUM(size),0) FROM hosted_sites WHERE user_id=?',[$uid])->fetchColumn();
        $total=(int)q('SELECT COALESCE(SUM(size),0) FROM hosted_sites')->fetchColumn();
        host_require($used-$old+$size<=HOST_ACCOUNT_LIMIT && $total-$old+$size<=HOST_TOTAL_LIMIT,'Hosting storage limit reached.',413);
        $now=time();
        q('INSERT INTO hosted_sites(slug,user_id,title,created,updated,size) VALUES(?,?,?,?,?,?)
           ON CONFLICT(slug) DO UPDATE SET title=excluded.title,updated=excluded.updated,size=excluded.size',[$slug,$uid,$title,$now,$now,$size]);
        q('DELETE FROM hosted_files WHERE slug=?',[$slug]);
        $insert=$db->prepare('INSERT INTO hosted_files(slug,path,mime,bytes) VALUES(?,?,?,?)');
        foreach($files as $path=>[$mime,$bytes]){
            $insert->bindValue(1,$slug); $insert->bindValue(2,$path); $insert->bindValue(3,$mime);
            $insert->bindValue(4,$bytes,PDO::PARAM_LOB); $insert->execute();
        }
        q('DELETE FROM hosted_events WHERE created<=?',[$now-600]);
        q('INSERT INTO hosted_events(user_id,created) VALUES(?,?)',[$uid,$now]);
        $db->exec('COMMIT');
    } catch (Throwable $e) {
        $db->exec('ROLLBACK'); throw $e;
    }
    return ['slug'=>$slug,'title'=>$title,'url'=>'/'.$slug.'/','count'=>count($files),'size'=>$size];
}
function host_site_files(string $slug): array {
    $files=[];
    foreach(q('SELECT path,bytes FROM hosted_files WHERE slug=? ORDER BY path',[$slug])->fetchAll() as $row) $files[$row['path']]=['base64'=>base64_encode($row['bytes'])];
    return $files;
}
function host_security(bool $runtime=false): void {
    header('X-Content-Type-Options: nosniff');
    header('Referrer-Policy: no-referrer');
    header('Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()');
    $cdn='https://unpkg.com https://cdn.jsdelivr.net';
    $script=$runtime?"'unsafe-inline' 'wasm-unsafe-eval' 'self' blob: $cdn":"'unsafe-inline' 'self' https: data: blob:";
    $extra=$runtime?"connect-src $cdn; worker-src blob:; frame-src 'self' data: blob:;":"connect-src 'none'; worker-src 'none'; frame-src 'none';";
    header("Content-Security-Policy: sandbox allow-scripts allow-forms; default-src 'none'; base-uri 'self'; form-action 'self'; script-src $script; style-src 'unsafe-inline' 'self' https: data:; img-src 'self' https: data: blob:; font-src 'self' https: data:; media-src 'self' https: data: blob:; $extra");
}
function host_e(string $s): string {return htmlspecialchars($s,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
function host_page(string $title,string $body,int $code=200): never {
    http_response_code($code);host_security();
    header('Content-Type: text/html; charset=utf-8');
    $t=host_e($title);
    echo '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'.$t.'</title><style>body{color:#152039;background:#f2f7fd;font:16px system-ui;margin:10vh auto;padding:24px;max-width:520px}a{color:#1749a0;display:inline-block;margin:8px 14px 8px 0}
:root[data-theme=light] body{background:linear-gradient(#f2f7ffdd,#edf4ff 550px),url(data:image/webp;base64,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) center top / max(100vw,800px) auto no-repeat,var(--bg)}
</style><main><h1>'.$t.'</h1>'.$body.'</main>';
    exit;
}
function host_runtime_script(): string {
    $cdn=json_encode([HOST_CDN, HOST_CDN_FALLBACK]);
    return 'const CDN='.$cdn.';' . <<<'JS'
onmessage=async event=>{
  try{
    // The packaged Emscripten build initializes DOM bindings even in a worker.
    globalThis.window=globalThis;
    globalThis.document={getElementById:()=>null,querySelector:()=>null};
    let php,runtime,error;
    for(const source of CDN){
      try{
        const {PhpBase}=await import(source+'PhpBase.mjs');
        php=new PhpBase(import(source+'php8.3-web.mjs'),{version:'8.3',autoTransaction:false});
        runtime=await php.binary;
        break;
      }catch(failure){error=failure}
    }
    if(!runtime)throw Error('Could not load PHP 8.3: '+String(error?.message||error));
    const files=event.data.files,path=event.data.path;
    runtime.FS.mkdirTree('/website');
    for(const [name,file] of Object.entries(files)){
      const filename='/website/'+name;
      runtime.FS.mkdirTree(filename.slice(0,filename.lastIndexOf('/')));
      runtime.FS.writeFile(filename,Uint8Array.from(atob(file.base64),c=>c.charCodeAt(0)));
    }
    let html='',errors='';
    php.onoutput=e=>{html+=e.detail[0];if(html.length>1048576)throw Error('PHP output exceeds 1 MiB.')};
    php.onerror=e=>{errors+=e.detail[0]};
    const parsed=new URLSearchParams(event.data.query||'');
    const args=JSON.stringify(Object.fromEntries(parsed));
    const phpString=s=>"'"+s.replaceAll('\\','\\\\').replaceAll("'","\\'")+"'";
    const entry='/website/'+path;
    const cwd=entry.slice(0,entry.lastIndexOf('/'));
    await php.run('<?php $_GET=json_decode('+phpString(args)+',true); $_SERVER["REQUEST_METHOD"]="GET"; chdir('+phpString(cwd)+'); require '+phpString(entry)+';');
    if(!html&&errors)throw Error(errors.slice(0,500));
    postMessage({html});
  }catch(error){postMessage({error:String(error.message||error).slice(0,600)})}
};
JS;
}
function host_php_page(string $entry,array $files,string $slug): never {
    host_security(true);
    header('Content-Type: text/html; charset=utf-8');header('Cache-Control: no-cache');
    $data=json_encode(['path'=>$entry,'files'=>$files,'query'=>$_SERVER['QUERY_STRING']??''],JSON_HEX_TAG|JSON_HEX_AMP|JSON_HEX_APOS|JSON_HEX_QUOT|JSON_INVALID_UTF8_SUBSTITUTE);
    $runner=json_encode(host_runtime_script(),JSON_HEX_TAG|JSON_HEX_AMP|JSON_HEX_APOS|JSON_HEX_QUOT);
    echo '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'.host_e($slug).'</title><style>html,body{margin:0;min-height:100%;font:16px system-ui}#status{margin:2rem}iframe{display:block;width:100%;height:100dvh;border:0}</style><p id="status" role="status">Starting PHP in your browser…</p><script>';
    echo "const input=$data, code=$runner;";
    echo <<<'JS'
const status=document.querySelector('#status');
const url=URL.createObjectURL(new Blob([code],{type:'text/javascript'}));
const worker=new Worker(url);
function stop(){worker.terminate();URL.revokeObjectURL(url);}
const timer=setTimeout(()=>{stop();status.textContent='PHP exceeded the browser runtime time limit or the runtime could not load.'},25000);
worker.onerror=()=>{clearTimeout(timer);stop();status.textContent='Could not start the isolated PHP runtime.';};
worker.onmessage=event=>{
  clearTimeout(timer);stop();
  if(event.data.error){status.textContent=event.data.error;return;}
  const frame=document.createElement('iframe');
  frame.title='Website';
  frame.setAttribute('sandbox','allow-scripts allow-forms');
  const doc=new DOMParser().parseFromString(event.data.html,'text/html');
  for(const base of doc.querySelectorAll('base'))base.remove();
  const base=doc.createElement('base');base.href=location.href;doc.head.prepend(base);
  frame.srcdoc='<!doctype html>'+doc.documentElement.outerHTML;
  status.replaceWith(frame);
};
worker.postMessage(input);
JS;
    echo '</script>';exit;
}
function host_public(string $requestPath): never {
    $parts=explode('/',trim($requestPath,'/'),2);
    $slug=host_slug(rawurldecode($parts[0]??''));
    $file=isset($parts[1])?rawurldecode($parts[1]):'';
    if($file!=='') $file=host_path($file);
    host_require((bool)q('SELECT 1 FROM hosted_sites WHERE slug=?',[$slug])->fetchColumn(),'Website not found.',404);
    if($file===''){
        $indexes=q("SELECT path FROM hosted_files WHERE slug=? AND path IN ('index.html','index.php') ORDER BY path",[$slug])->fetchAll(PDO::FETCH_COLUMN);
        if(count($indexes)===2)host_page('Choose a site entry','<a href="/'.$slug.'/index.html">Open HTML</a><a href="/'.$slug.'/index.php">Open PHP</a>');
        if(!str_ends_with($requestPath,'/')){header('Location: /'.$slug.'/',true,302);exit;}
        $file=$indexes[0]??'index.html';
    }
    $row=q('SELECT mime,bytes FROM hosted_files WHERE slug=? AND path=?',[$slug,$file])->fetch();
    host_require((bool)$row,'File not found.',404);
    if(str_starts_with($row['mime'],'text/html')||$row['mime']==='application/x-astheral-php'){
        if(($_SERVER['REQUEST_METHOD']??'GET')==='GET'){
            try {q("INSERT INTO hosted_views(slug,day,views) VALUES(?,?,1) ON CONFLICT(slug,day) DO UPDATE SET views=views+1",[$slug,gmdate('Y-m-d')]);} catch(Throwable $e){}
        }
    }
    if($row['mime']==='application/x-astheral-php')host_php_page($file,host_site_files($slug),$slug);
    host_security();
    header('Content-Type: '.$row['mime']);header('Cache-Control: no-cache');
    if($row['mime']==='application/pdf')header('Content-Disposition: attachment');
    if(($_SERVER['REQUEST_METHOD']??'GET')!=='HEAD')echo $row['bytes'];
    exit;
}

if(defined('ASTHERAL_HOST_LIBRARY')) return;
define('ASTHERAL_CHAT_BOOTSTRAP',true);
require __DIR__.'/index.php';
host_init();
$path=parse_url($_SERVER['REQUEST_URI']??'/host.php',PHP_URL_PATH)?:'/host.php';
if(!in_array($path,['/host.php','/index.php'],true)){
    session_write_close();
    try{host_public($path);}catch(Throwable $e){
        $code=$e instanceof RuntimeException&&in_array($e->getCode(),[400,404],true)?$e->getCode():500;
        host_page($code===500?'Could not open the website':$e->getMessage(),'<a href="/host.php">Astheral Host</a>',$code);
    }
}
if(isset($_GET['a'])){
    $action=$_GET['a'];$uid=(int)($_SESSION['uid']??0);
    try{
        host_require($uid>0,'Sign in to Astheral first.',401);
        if($action==='sites'){
            $sites=q('SELECT s.slug,s.title,s.size,s.updated,COALESCE((SELECT SUM(v.views) FROM hosted_views v WHERE v.slug=s.slug),0) AS views FROM hosted_sites s WHERE s.user_id=? ORDER BY s.updated DESC',[$uid])->fetchAll();
            out(['sites'=>$sites]);
        }
        host_require($_SERVER['REQUEST_METHOD']==='POST'&&hash_equals($_SESSION['csrf'],$_SERVER['HTTP_X_CSRF']??''),'Session expired. Reload the page.',403);
        if(session_status()===PHP_SESSION_ACTIVE)session_write_close();
        host_require((int)($_SERVER['CONTENT_LENGTH']??0)<=4500000,'Upload exceeds the request limit.',413);
        $in=json_decode(file_get_contents('php://input',false,null,0,4500001)?:'{}',true);
        host_require(is_array($in),'Invalid request.');
        $slug=host_slug((string)($in['slug']??''));
        if($action==='deploy')out(['site'=>host_deploy($uid,$slug,(string)($in['title']??''),(array)($in['files']??[]),!empty($in['replace']))]);
        $site=q('SELECT slug,title FROM hosted_sites WHERE slug=? AND user_id=?',[$slug,$uid])->fetch();
        host_require((bool)$site,'Website not found.',404);
        if($action==='analytics'){
            out(['views'=>q('SELECT day,views FROM hosted_views WHERE slug=? AND day>=? ORDER BY day DESC',[$slug,gmdate('Y-m-d',time()-30*86400)])->fetchAll()]);
        }
        if($action==='open'){
            $site['files']=host_site_files($slug);
            $site['views']=q('SELECT day,views FROM hosted_views WHERE slug=? AND day>=? ORDER BY day DESC',[$slug,gmdate('Y-m-d',time()-30*86400)])->fetchAll();
            out(['site'=>$site]);
        }
        if($action==='delete'){q('DELETE FROM hosted_sites WHERE slug=? AND user_id=?',[$slug,$uid]);out(['ok'=>true]);}
        fail('Unknown action.',404);
    }catch(Throwable $e){
        $code=$e instanceof RuntimeException&&in_array($e->getCode(),[400,401,403,404,409,413,429],true)?$e->getCode():500;
        fail($code===500?'Could not complete the hosting operation.':$e->getMessage(),$code);
    }
}
header('Cache-Control: no-store');
$csrf=$_SESSION['csrf'];
$account=isset($_SESSION['uid'])?q('SELECT username FROM users WHERE id=?',[(int)$_SESSION['uid']])->fetchColumn():false;
?>
<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Astheral Host</title>
<style>
:root{color-scheme:dark;--bg:#0c1322;--surface:#131e31;--mut:#a5b6d0;--fg:#eff4ff;--line:#2a3c56;--accent:#a8c4ff;--on:#14264b}
:root[data-theme=light]{color-scheme:light;--bg:#edf4ff;--surface:#fcfdff;--mut:#465975;--fg:#182840;--line:#bacce3;--accent:#224fae;--on:#fff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 72% 0%,#4c79b327,transparent 55%),var(--bg);color:var(--fg);font:15px/1.5 system-ui}
a{color:var(--accent)}button,input,textarea,select{font:inherit;color:inherit}button,input,textarea,select{border:1px solid var(--line);border-radius:5px;background:var(--surface);padding:8px 10px}button{cursor:pointer}button:disabled{opacity:.5;cursor:wait}button.primary{background:var(--accent);border-color:var(--accent);color:var(--on);font-weight:650}:focus-visible{outline:2px solid var(--accent);outline-offset:2px}label{display:grid;gap:5px;margin:0}header{border-bottom:1px solid var(--line);background:var(--surface);padding:12px clamp(14px,4vw,42px);display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}header nav{display:flex;gap:10px;align-items:center;flex-wrap:wrap}header strong{font-size:18px}main{max-width:1320px;margin:auto;padding:22px clamp(14px,4vw,42px)}h1{margin:0 0 6px;font-size:clamp(25px,5vw,38px);letter-spacing:-.04em}h2{font-size:16px;margin:0 0 10px}.note,small{color:var(--mut)}p{margin:0 0 10px}.layout{display:grid;grid-template-columns:240px minmax(0,1fr);gap:14px;margin-top:20px}.panel{border:1px solid var(--line);background:var(--surface);border-radius:8px;padding:14px;min-width:0}.toolbar,.meta-fields{display:flex;flex-wrap:wrap;gap:8px;align-items:end;margin-bottom:10px}.meta-fields label{flex:1;min-width:145px}.meta-fields input{width:100%}.work{display:grid;grid-template-columns:140px minmax(0,1fr);gap:10px}.files,.sites{display:grid;align-content:start;gap:5px;overflow:auto;max-height:420px}.file,.site{text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file[aria-pressed=true],.site[aria-pressed=true]{border-color:var(--accent);color:var(--accent)}textarea#code{width:100%;resize:vertical;min-height:320px;background:var(--bg);font:14px/1.6 ui-monospace,monospace;tab-size:2}iframe{width:100%;min-height:360px;background:white;border:1px solid var(--line);border-radius:5px}.auth{max-width:430px;margin:24px auto}.auth form{display:grid;gap:10px}.status{min-height:24px;margin:5px 0}.stat{border-top:1px solid var(--line);padding-top:8px;margin-top:10px}.stat table{width:100%;font-size:13px}.stat td:last-child{text-align:right}dialog{width:min(800px,calc(100vw - 24px));max-height:calc(100dvh - 24px);color:var(--fg);background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px}dialog::backdrop{background:#0009}dialog .toolbar{justify-content:space-between}dialog iframe{height:65dvh}details{margin-top:8px}summary{cursor:pointer}.hidden,[hidden]{display:none!important}@media(max-width:760px){.layout{grid-template-columns:1fr}.sites{grid-template-columns:repeat(2,minmax(0,1fr));max-height:160px}}@media(max-width:480px){.work{grid-template-columns:1fr}.files{grid-template-columns:repeat(2,minmax(0,1fr));max-height:130px}textarea#code{min-height:240px}}

body>header{height:auto;min-height:58px;background:var(--surface);position:relative;z-index:1}
body>header nav{gap:12px}body>header nav a{text-decoration:none;font-size:13px}
body>header nav span{color:var(--mut);font-size:13px}
.host-layout{display:grid;grid-template-columns:minmax(190px,230px) minmax(0,1fr);gap:22px;min-height:460px}
.site-rail{align-self:start;min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.rail-heading,.files-heading{display:flex;align-items:center;justify-content:space-between;gap:7px;padding:10px 12px;border-bottom:1px solid var(--line)}
.rail-heading h2,.files-heading h2{margin:0;font-size:13px}.rail-heading button,.files-heading button{font-size:12px;padding:5px 8px}
.site-rail .sites{padding:6px;display:grid;gap:4px;max-height:65dvh}
.site-rail .site{display:grid;gap:1px;border:1px solid transparent;background:transparent;padding:8px 9px;min-width:0}
.site-rail .site[aria-pressed=true],.site-rail .site:hover{border-color:var(--line);background:var(--bg)}
.site-rail .site strong,.site-rail .site small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rail-empty{padding:5px 7px;margin:0;font-size:13px}
.host-main{min-width:0}
.welcome{border:1px solid var(--line);border-radius:9px;background:var(--surface);padding:clamp(24px,6vw,65px);min-height:300px;display:grid;align-content:center;justify-items:start}
.welcome .overline{letter-spacing:.13em;text-transform:uppercase;color:var(--accent);font-size:11px;font-weight:650;margin:0 0 9px}
.welcome .note{margin:4px 0 18px}
.project{border:1px solid var(--line);background:var(--surface);border-radius:9px;min-width:0}
.project-heading{padding:14px 16px;display:flex;align-items:center;gap:12px;justify-content:space-between;flex-wrap:wrap}
.project-heading h1{font-size:clamp(21px,4vw,32px);margin:4px 0 2px;overflow-wrap:anywhere}
.project-state{font-size:11px;font-weight:650;color:var(--accent);text-transform:uppercase;letter-spacing:.06em}
.project-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.project-actions a,.project-actions button{font-size:13px}
.project-actions a{padding:7px 9px;border:1px solid var(--line);border-radius:5px;text-decoration:none}
.site-more{position:relative;margin:0}.site-more summary{padding:7px;border:1px solid var(--line);border-radius:5px;font-size:13px}
.site-more button{position:absolute;right:0;top:calc(100% + 5px);white-space:nowrap;z-index:2;color:#fa818d}
:root[data-theme=light] .site-more button{color:#a82e43}
.project-tabs{display:flex;gap:4px;padding:0 13px;border-block:1px solid var(--line);min-width:0}
.project-tabs button{background:transparent;border:0;border-bottom:2px solid transparent;border-radius:0;padding:9px 10px;font-size:13px}
.project-tabs button[aria-pressed=true]{color:var(--accent);border-bottom-color:var(--accent);font-weight:650}
.view-panel{min-width:0}.work{grid-template-columns:minmax(135px,175px) minmax(0,1fr);gap:0}
.project-files{min-width:0;border-right:1px solid var(--line)}
.project-files .files{padding:6px;gap:3px;max-height:300px}
.project-files .file{border:1px solid transparent;background:transparent;font:12px ui-monospace,monospace;min-height:32px;padding:6px}
.project-files .file[aria-pressed=true],.project-files .file:hover{border-color:var(--line);background:var(--bg)}
.file-upload{padding:0 10px 9px;font-size:12px}.file-upload>div{display:grid;gap:4px;padding-top:6px}.file-upload button{padding:5px}
.source-pane{min-width:0}.source-heading{display:flex;align-items:center;justify-content:space-between;gap:5px;padding:5px 9px}
.source-heading label{font:12px ui-monospace,monospace;overflow-wrap:anywhere;color:var(--mut)}
#remove{font-size:11px;padding:5px 7px;white-space:nowrap}
textarea#code{display:block;border:0;border-top:1px solid var(--line);border-radius:0;min-height:clamp(320px,55dvh,600px);padding:12px}
textarea#code:focus-visible{outline-offset:-2px}#binary{padding:10px}
.preview-panel,.analytics-panel{padding:12px}
.preview-toolbar,.analytics-title{display:flex;justify-content:space-between;align-items:flex-end;gap:8px;margin-bottom:10px}
.preview-toolbar label{font-size:12px}.preview-toolbar select{min-width:130px}
.preview-panel iframe{display:block;height:56dvh;min-height:280px}
.analytics-title{align-items:flex-start}.analytics-title h2{margin:0 0 3px}.analytics-title p{font-size:13px}
.analytics-total{border-bottom:1px solid var(--line);padding:4px 0 9px;margin-bottom:9px}.analytics-total strong{font-size:26px}
#analytics table{width:100%;text-align:left;border-collapse:collapse;font-size:13px}#analytics th,#analytics td{border-bottom:1px solid var(--line);padding:5px 4px}#analytics tr>*:last-child{text-align:right}
.status:empty{min-height:0;margin:0}.host-footer{margin-top:12px;font-size:12px}
dialog{width:min(430px,calc(100vw - 24px));padding:14px}.dialog-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:12px}.dialog-heading h2{margin:0}.dialog-heading button{padding:5px 8px}
#publish-form,#add-form,.new-choices{display:grid;gap:10px}.new-choices button{display:grid;text-align:left;gap:4px}.new-choices small{display:block}
@media(max-width:760px){.host-layout{grid-template-columns:1fr;gap:12px}.site-rail .sites{grid-template-columns:repeat(2,minmax(0,1fr));max-height:120px}.site-rail .sites:has(.rail-empty){grid-template-columns:1fr}}
@media(max-width:500px){.work{grid-template-columns:1fr}.project-files{border-right:0;border-bottom:1px solid var(--line)}.project-files .files{grid-template-columns:repeat(2,minmax(0,1fr));max-height:100px}.file-upload>div{display:flex;flex-wrap:wrap}.project-heading{padding:10px}.project-heading h1{margin:2px 0}.preview-panel iframe{height:49dvh}}

</style>
</head>
<body>
<header><strong>Astheral Host</strong><nav><a href="/index.php">Back to chat</a><button id="theme" type="button">Cloudy light</button><?php if($account): ?><span><?=host_e((string)$account)?></span><button id="signout" type="button">Sign out</button><?php endif ?></nav></header>
<main>
<?php if(!$account): ?>
<section class="panel auth"><h1>Sign in to Host</h1><p class="note">Use your Astheral account, or make one here.</p>
<div class="toolbar"><button id="login-tab">Sign in</button><button id="signup-tab">Create account</button></div>
<form id="auth"><label id="email-label" hidden>Email<input type="email" id="email" autocomplete="email"></label><label><span id="login-label">Email or username</span><input id="login" autocomplete="username" required></label><label>Password<input type="password" id="password" autocomplete="current-password" required></label><p class="status" id="auth-status" role="status"></p><button class="primary" id="auth-submit">Sign in</button></form></section>
<?php else: ?>
<div class="host-layout">
  <aside class="site-rail" aria-label="Your websites">
    <div class="rail-heading"><h2>Your sites</h2><button id="site-new" type="button" aria-haspopup="dialog">+ New</button></div>
    <div id="sites" class="sites"></div>
  </aside>
  <section class="host-main">
    <div id="welcome" class="welcome">
      <h1>Website workspace</h1>
      <p class="note">Open one of your sites, or start a new project.</p>
      <button id="welcome-new" class="primary" type="button">New website</button>
    </div>
    <section id="project" class="project" hidden>
      <div class="project-heading">
        <div>
          <span id="project-state" class="project-state">Draft</span>
          <h1 id="project-title">Untitled website</h1>
          <span id="project-path" class="note"></span>
        </div>
        <div class="project-actions">
          <a id="visit" target="_blank" rel="noopener" hidden>Visit site ↗</a>
          <button id="deploy" class="primary" type="button">Publish</button>
          <details id="site-more" class="site-more" hidden><summary aria-label="Site options">More</summary><button id="delete" type="button">Delete site</button></details>
        </div>
      </div>
      <nav class="project-tabs" aria-label="Project views">
        <button id="view-files" type="button" data-view="files" aria-pressed="true">Files</button>
        <button id="preview" type="button" data-view="preview" aria-pressed="false">Preview</button>
        <button id="view-analytics" type="button" data-view="analytics" aria-pressed="false">Analytics</button>
      </nav>
      <div id="panel-files" class="view-panel">
        <div class="work">
          <aside class="project-files" aria-label="Project files">
            <div class="files-heading"><h2>Project files</h2><button id="add" type="button" title="Add file">+ Add</button></div>
            <div id="files" class="files"></div>
            <details class="file-upload"><summary>Upload files</summary><div><button id="upload" type="button">Choose files</button><button id="folder" type="button">Choose folder</button></div></details>
            <input id="upload-input" type="file" multiple hidden><input id="folder-input" type="file" multiple webkitdirectory hidden>
          </aside>
          <div class="source-pane">
            <div class="source-heading"><label id="edit-label" for="code">Source</label><button id="remove" type="button">Remove file</button></div>
            <textarea id="code" spellcheck="false" autocomplete="off" autocapitalize="none"></textarea>
            <p id="binary" class="note" hidden>Binary file. Replace it by uploading it again.</p>
          </div>
        </div>
      </div>
      <div id="panel-preview" class="view-panel preview-panel" hidden>
        <div class="preview-toolbar"><label>Entry file<select id="preview-entry"></select></label><button id="refresh-preview" type="button">Refresh</button></div>
        <div id="preview-slot"></div>
      </div>
      <section id="panel-analytics" class="view-panel analytics-panel" hidden>
        <div class="analytics-title"><div><h2>Page views</h2><p class="note">Published traffic in the last 30 days (UTC).</p></div><button id="refresh-analytics" type="button">Refresh</button></div>
        <div id="analytics"></div>
      </section>
    </section>
    <p id="status" class="status" role="status"></p>
  </section>
</div>
<footer class="host-footer"><details><summary>Limits and PHP behavior</summary><p class="note">Up to 60 files, 768 KiB per file, 3 MiB per site, 12 sites and 12 MiB per account. Up to 10 publishes or updates in 10 minutes. PHP runs in the visitor’s browser. Its source is sent to visitors, so keep secrets out of published files. Server sessions and databases are unavailable on hosted sites.</p></details></footer>
<dialog id="new-dialog" aria-labelledby="new-title">
  <div class="dialog-heading"><h2 id="new-title">New website</h2><button type="button" data-close="new-dialog" aria-label="Close">✕</button></div>
  <div class="new-choices"><button id="new" type="button"><strong>HTML website</strong><small>Start with an HTML page and add CSS, JavaScript, or assets.</small></button><button id="new-php" type="button"><strong>PHP website</strong><small>Start with an index.php that runs in the browser.</small></button></div>
</dialog>
<dialog id="publish-dialog" aria-labelledby="publish-title">
  <div class="dialog-heading"><h2 id="publish-title">Publish website</h2><button type="button" data-close="publish-dialog" aria-label="Close">✕</button></div>
  <form id="publish-form">
    <label>Site address<input id="slug" maxlength="48" placeholder="dinosaurs" spellcheck="false" required></label>
    <label>Site title<input id="title" maxlength="90" placeholder="Dinosaur park"></label>
    <p class="note">Published files will be available publicly at this address.</p>
    <p id="publish-status" class="status" role="status"></p>
    <button id="publish-confirm" class="primary" type="submit">Publish website</button>
  </form>
</dialog>
<dialog id="file-dialog" aria-labelledby="file-title"><div class="dialog-heading"><h2 id="file-title">Add a file</h2><button type="button" id="cancel-file" aria-label="Close">✕</button></div><form id="add-form"><label>File path<input id="file-name" placeholder="assets/style.css" required maxlength="180"></label><p class="status" id="file-status" role="status"></p><button class="primary">Add file</button></form></dialog>
<?php endif ?>
</main>
<script>
const $=s=>document.querySelector(s);
const csrf=<?=json_encode($csrf,JSON_HEX_TAG)?>;
const signedIn=<?=json_encode((bool)$account)?>;
const phpRunner=<?=json_encode(host_runtime_script(),JSON_HEX_TAG|JSON_HEX_AMP|JSON_HEX_APOS|JSON_HEX_QUOT)?>;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function theme(mode){document.documentElement.dataset.theme=mode;$('#theme').textContent=mode==='dark'?'Cloudy light':'Dark mode';localStorage.setItem('astheral-host-theme',mode)}
theme(localStorage.getItem('astheral-host-theme')==='light'?'light':'dark');
$('#theme').onclick=()=>theme(document.documentElement.dataset.theme==='dark'?'light':'dark');
async function call(url,data){
  const options=data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF':csrf},body:JSON.stringify(data)};
  const result=await fetch(url,options);const json=await result.json().catch(()=>({}));
  if(!result.ok)throw Error(json.error||'Request failed.');return json;
}
const host=(a,d)=>call('/host.php?a='+a,d);
if(!signedIn){
  let signUp=false;
  function mode(value){signUp=value;$('#email-label').hidden=!value;$('#email').required=value;$('#login-label').textContent=value?'Username':'Email or username';$('#password').autocomplete=value?'new-password':'current-password';$('#auth-submit').textContent=value?'Create account':'Sign in'}
  $('#login-tab').onclick=()=>mode(false);$('#signup-tab').onclick=()=>mode(true);
  $('#auth').onsubmit=async e=>{
    e.preventDefault();$('#auth-submit').disabled=true;$('#auth-status').textContent='';
    try{await call('/index.php?a='+(signUp?'signup':'login'),{login:$('#login').value,username:$('#login').value,email:$('#email').value,password:$('#password').value});location.reload()}
    catch(err){$('#auth-status').textContent=err.message}finally{$('#auth-submit').disabled=false}
  };
}else{
  let current='',active='',files=Object.create(null),dates=[],dirty=false,loadId=0;
  const editor=$('#code'),status=$('#status'),decoder=new TextDecoder(),encoder=new TextEncoder();
  const textFile=name=>/\.(html?|css|m?js|php|txt|md|json|webmanifest|svg)$/i.test(name);
  const type=name=>({html:'text/html',htm:'text/html',css:'text/css',js:'text/javascript',mjs:'text/javascript',svg:'image/svg+xml',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp',gif:'image/gif',woff2:'font/woff2',woff:'font/woff',mp3:'audio/mpeg',mp4:'video/mp4',json:'application/json'})[name.split('.').pop().toLowerCase()]||'application/octet-stream';
  function encode(bytes){let raw='';for(let i=0;i<bytes.length;i+=8192)raw+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(raw)}
  function decode(raw){return decoder.decode(Uint8Array.from(atob(raw),c=>c.charCodeAt(0)))}
  function setFile(name,text){files[name]={base64:encode(encoder.encode(text))}}
  function validPath(name){return name.length<=180&&/^[a-z0-9_-][a-z0-9_.-]*(\/[a-z0-9_-][a-z0-9_.-]*){0,8}$/i.test(name)&&/\.(html?|php|css|m?js|txt|md|json|webmanifest|svg|jpe?g|png|gif|webp|avif|ico|woff2?|ttf|mp3|ogg|mp4|webm|pdf)$/i.test(name)}
  function select(name){
    active=name;
    $('#files').innerHTML=Object.keys(files).map(n=>`<button class="file" data-file="${esc(n)}" aria-pressed="${n===name}">${esc(n)}</button>`).join('');
    const text=name&&textFile(name);
    $('#edit-label').textContent=name||'Source';editor.hidden=Boolean(name&&!text);$('#binary').hidden=!(name&&!text);editor.disabled=!text;editor.value=text?decode(files[name].base64):'';
    $('#remove').disabled=!name;
  }
  function showAnalytics(){
    const a=$('#analytics');
    if(!current){a.innerHTML='<p class="note">Publish this website to start recording page views.</p>';return}
    const total=dates.reduce((sum,item)=>sum+Number(item.views),0);
    const rows=dates.map(({day,views})=>`<tr><td>${esc(day)}</td><td>${Number(views)}</td></tr>`).join('');
    a.innerHTML=`<div class="analytics-total"><strong>${total.toLocaleString()}</strong> <span class="note">page views</span></div>`+(rows?'<table><thead><tr><th scope="col">Date (UTC)</th><th scope="col">Views</th></tr></thead><tbody>'+rows+'</tbody></table>':'<p class="note">No visits recorded yet.</p>');
  }
  function showState(){
    $('#deploy').textContent=current?'Publish changes':'Publish';$('#slug').readOnly=!!current;
    $('#project-title').textContent=$('#title').value.trim()||current||'Untitled website';
    $('#project-state').textContent=current?(dirty?'Unpublished changes':'Published'):'Draft';
    $('#project-path').textContent=current?'/'+current+'/':'';
    $('#visit').hidden=!current;$('#visit').href=current?'/'+current+'/':'#';$('#site-more').hidden=!current;
    $('#refresh-analytics').disabled=!current;
    showAnalytics();
  }
  function showProject(next='files'){
    $('#welcome').hidden=true;$('#project').hidden=false;setView(next);
  }
  function setView(next){
    for(const name of ['files','preview','analytics']){
      $('#panel-'+name).hidden=name!==next;
      document.querySelector('[data-view="'+name+'"]').setAttribute('aria-pressed',name===next);
    }
    if(next==='preview')setupPreview();
    else $('#preview-slot').replaceChildren();
    if(next==='analytics')showAnalytics();
  }
  function change(){dirty=true;showState()}
  function allowSwitch(){return !dirty||confirm('Switch projects? Unpublished changes will be lost.')}
  async function list(){
    try{const {sites}=await host('sites');$('#sites').innerHTML=sites.map(s=>`<button class="site" data-site="${esc(s.slug)}" aria-pressed="${s.slug===current}"><strong>${esc(s.title)}</strong><small>/${esc(s.slug)}/</small></button>`).join('')||'<p class="note rail-empty">No published sites.</p>'}
    catch(error){status.textContent=error.message}
  }
  async function open(slug){
    status.textContent='';
    const id=++loadId;
    try{
      const {site}=await host('open',{slug});
      if(id!==loadId)return;
      current=site.slug;files=Object.assign(Object.create(null),site.files);dates=site.views;
      $('#slug').value=site.slug;$('#title').value=site.title;dirty=false;
      select(files['index.html']?'index.html':Object.keys(files)[0]);showState();showProject();await list();
    }catch(error){if(id===loadId)status.textContent=error.message}
  }
  async function refreshAnalytics(){
    if(!current)return;
    const slug=current,button=$('#refresh-analytics');button.disabled=true;
    try{const {views}=await host('analytics',{slug});if(current===slug){dates=views;showAnalytics()}}
    catch(err){status.textContent=err.message}finally{button.disabled=!current}
  }
  function fresh(php=false){
    loadId++;current='';files=Object.create(null);dates=[];dirty=false;$('#slug').value='';$('#title').value='';
    const name=php?'index.php':'index.html';
    setFile(name,php?'<'+'?php\ndeclare(strict_types=1);\n$name = $_GET["name"] ?? "world";\necho "<h1>Hello, " . htmlspecialchars($name, ENT_QUOTES, \'UTF-8\') . "!</h1>";\n':'<!doctype html>\n<html lang="en">\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1">\n  <title>Home</title>\n</head>\n<body>\n  <h1>My website</h1>\n</body>\n</html>');
    select(name);showState();showProject();status.textContent='';list();
  }
  editor.oninput=()=>{if(active){setFile(active,editor.value);change()}};
  $('#sites').onclick=e=>{const item=e.target.closest('[data-site]');if(item&&allowSwitch())open(item.dataset.site)};
  $('#files').onclick=e=>{const item=e.target.closest('[data-file]');if(item)select(item.dataset.file)};
  function openNew(){if(allowSwitch())$('#new-dialog').showModal()}
  $('#site-new').onclick=$('#welcome-new').onclick=openNew;
  $('#new').onclick=()=>{$('#new-dialog').close();fresh()};
  $('#new-php').onclick=()=>{$('#new-dialog').close();fresh(true)};
  for(const button of document.querySelectorAll('[data-close]'))button.onclick=()=>$('#'+button.dataset.close).close();
  for(const button of document.querySelectorAll('[data-view]'))button.onclick=()=>setView(button.dataset.view);
  $('#refresh-analytics').onclick=refreshAnalytics;
  window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue=''}});

  $('#add').onclick=()=>{$('#file-name').value='';$('#file-status').textContent='';$('#file-dialog').showModal()};
  $('#cancel-file').onclick=()=>$('#file-dialog').close();
  $('#add-form').onsubmit=e=>{
    e.preventDefault();const name=$('#file-name').value.trim();
    if(!validPath(name)||files[name]||Object.keys(files).length>=60){$('#file-status').textContent='Use a supported, unique path and keep the project under 60 files.';return}
    setFile(name,name.endsWith('.php')?'<'+'?php echo "Hello from PHP";':'');select(name);change();$('#file-dialog').close();editor.focus();
  };
  $('#remove').onclick=()=>{if(active){delete files[active];select(Object.keys(files)[0]||'');change()}};
  async function addFiles(input,folder){
    let last='',errors=0;
    for(const file of input.files){
      const name=folder?file.webkitRelativePath.split('/').slice(1).join('/'):file.name;
      if(!validPath(name)||file.size>786432||(!files[name]&&Object.keys(files).length>=60)){errors++;continue}
      files[name]={base64:encode(new Uint8Array(await file.arrayBuffer()))};last=name;
    }
    input.value='';
    if(last){select(last);change()}status.textContent=errors?errors+' file(s) skipped because of file type, path, count, or size limits.':'Files added.';
  }
  for(const [button,input,folder] of [['upload','upload-input',false],['folder','folder-input',true]]){
    $('#'+button).onclick=()=>$('#'+input).click();$('#'+input).onchange=e=>addFiles(e.target,folder).catch(err=>status.textContent=err.message);
  }
  $('#deploy').onclick=()=>{
    $('#publish-status').textContent='';
    $('#publish-title').textContent=current?'Publish changes':'Publish website';
    $('#publish-confirm').textContent=current?'Publish changes':'Publish website';
    $('#publish-dialog').showModal();
  };
  $('#publish-form').onsubmit=async e=>{
    e.preventDefault();
    const button=$('#publish-confirm'),notice=$('#publish-status');
    button.disabled=true;notice.textContent='Publishing…';
    try{
      const {site}=await host('deploy',{slug:$('#slug').value,title:$('#title').value,files,replace:!!current});
      dirty=false;$('#publish-dialog').close();
      await open(site.slug);status.textContent='Published at '+site.url;
    }catch(error){notice.textContent=error.message}
    finally{button.disabled=false}
  };
  $('#delete').onclick=async()=>{
    if(!current||!confirm('Delete /'+current+'/? The public link will stop working.'))return;
    try{await host('delete',{slug:current});current='';dirty=false;$('#project').hidden=true;$('#welcome').hidden=false;$('#preview-slot').replaceChildren();await list();status.textContent='Site deleted.'}catch(error){status.textContent=error.message}
  };
  $('#signout').onclick=async()=>{await call('/index.php?a=logout',{});location.reload()};
  function previewSource(html,entry,project=files){
    const doc=new DOMParser().parseFromString(html,'text/html');
    for(const tag of doc.querySelectorAll('base,meta[http-equiv]'))tag.remove();
    function local(value,from=entry){
      if(!value||/^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i.test(value))return null;
      const url=new URL(value,'https://local.invalid/'+from);
      return decodeURIComponent(url.pathname.slice(1));
    }
    function cssAssets(source,from){return source.replace(/url\(\s*["']?([^"'()]+)["']?\s*\)/g,(whole,value)=>{
      const path=local(value.trim(),from);return path&&project[path]?'url("data:'+type(path)+';base64,'+project[path].base64+'")':whole;
    })}
    for(const tag of doc.querySelectorAll('[src],[poster],link[href]')){
      const attr=tag.hasAttribute('src')?'src':tag.hasAttribute('poster')?'poster':'href',path=local(tag.getAttribute(attr));
      if(!path||!project[path])continue;
      if(tag.tagName==='LINK'&&tag.rel==='stylesheet'){
        const style=doc.createElement('style');style.textContent=cssAssets(decode(project[path].base64),path);tag.replaceWith(style);
      }else tag.setAttribute(attr,'data:'+type(path)+';base64,'+project[path].base64);
    }
    const policy=doc.createElement('meta');policy.httpEquiv='Content-Security-Policy';policy.content="default-src 'none'; script-src 'unsafe-inline' data:; style-src 'unsafe-inline' data:; img-src data:; font-src data:; media-src data:; form-action 'none'; base-uri 'none'";
    doc.head.prepend(policy);
    return '<!doctype html>'+doc.documentElement.outerHTML;
  }
  function phpPreview(entry){
    const stringify=x=>JSON.stringify(x).replace(/</g,'\\u003c');
    const config=stringify({files,entry}),worker=stringify(phpRunner);
    const runtime=`const status=document.querySelector('p');const config=${config};const u=URL.createObjectURL(new Blob([${worker}],{type:'text/javascript'}));const runner=new Worker(u);
    const timer=setTimeout(()=>{runner.terminate();status.textContent='PHP runtime timed out.'},25000);
    runner.onerror=()=>{clearTimeout(timer);runner.terminate();status.textContent='Could not start the PHP runtime.'};
    runner.onmessage=e=>{clearTimeout(timer);runner.terminate();URL.revokeObjectURL(u);if(e.data.error){status.textContent=e.data.error;return;}
    const frame=document.createElement('iframe');frame.setAttribute('sandbox','allow-scripts');frame.style.cssText='width:100%;height:96vh;border:0';frame.title='PHP output';
    frame.srcdoc=(${previewSource.toString().replace('project=files','project=config.files').replaceAll('type(path)','fileType(path)').replaceAll('decode(project[path].base64)','decodeText(project[path].base64)')})(e.data.html,config.entry);status.replaceWith(frame);};
    const decodeText=x=>new TextDecoder().decode(Uint8Array.from(atob(x),c=>c.charCodeAt(0)));
    const fileType=${type.toString()};runner.postMessage({path:config.entry,files:config.files});`;
    return '<!doctype html><meta charset=utf-8><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\' \'wasm-unsafe-eval\' blob: data: https://unpkg.com https://cdn.jsdelivr.net; connect-src https://unpkg.com https://cdn.jsdelivr.net; worker-src blob:; frame-src data: blob:; style-src \'unsafe-inline\' data:; img-src data:"><p>Starting PHP in your browser…</p><script>'+runtime.replace(/<\/script/gi,'<\\/script')+'</scr'+'ipt>';
  }
  function paintPreview(){
    const name=$('#preview-entry').value;
    const frame=document.createElement('iframe');
    frame.id='preview-frame';frame.title='Website preview';
    frame.setAttribute('sandbox','allow-scripts allow-forms');
    try{
      frame.srcdoc=!name?'<p>Add an HTML or PHP file to preview.</p>':name.endsWith('.php')?phpPreview(name):previewSource(decode(files[name].base64),name);
    }catch(err){frame.srcdoc='<p>'+esc(err.message)+'</p>'}
    $('#preview-slot').replaceChildren(frame);
  }
  function setupPreview(){
    const entries=Object.keys(files).filter(p=>/\.(html?|php)$/i.test(p));
    const select=$('#preview-entry'),previous=select.value;
    select.innerHTML=entries.map(p=>`<option value="${esc(p)}">${esc(p)}</option>`).join('');
    $('#refresh-preview').disabled=select.disabled=!entries.length;
    if(!entries.length){paintPreview();return}
    select.value=entries.includes(active)?active:entries.includes(previous)?previous:entries[0];
    paintPreview();
  }
  $('#preview-entry').onchange=$('#refresh-preview').onclick=paintPreview;
  list();
  const requested=new URLSearchParams(location.search).get('site');
  if(requested)open(requested);
}
</script></body></html>
