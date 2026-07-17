var h=require('http'),f=require('fs');
h.createServer(function(q,r){
  r.setHeader('Content-Type','text/html;charset=utf-8');
  r.setHeader('Cache-Control','no-cache,no-store,must-revalidate');
  r.setHeader('Pragma','no-cache');
  r.setHeader('Expires','0');
  r.end(f.readFileSync('E:/AI/menu/index.html'))
}).listen(8902)
