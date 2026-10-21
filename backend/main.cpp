#include "httplib.h"
#include "json.hpp"
#include <iostream>
#include <regex>
#include <queue>
#include <unordered_map>
#include <set>
#include <sstream>
#include <cmath>
using json = nlohmann::json;
#include "intent.hpp"
#include "workflow.hpp"
struct Port { std::string name, type; };
struct Spec { std::vector<Port> inputs, outputs; };
const std::map<std::string, Spec> specs = {
 {"component", {{{"dependency","object"}}, {{"object","object"}}}},
 {"mesh", {{}, {{"mesh","mesh"}}}},
 {"variable", {{{"mesh","mesh"}}, {{"field","field"}}}},
 {"diffusion", {{{"field","field"}}, {{"operator","operator"}}}},
 {"boundary", {{{"field","field"}}, {{"constraint","constraint"}}}},
 {"solver", {{{"operator","operator"},{"constraint","constraint"}}, {{"solution","solution"}}}},
 {"output", {{{"solution","solution"}}, {}}}
};
json defaults(const std::string &kind) {
 if(kind=="mesh") return {{"dim",2},{"nx",20},{"ny",20}};
 if(kind=="variable") return {{"name","u"}};
 if(kind=="solver") return {{"type","Steady"},{"solve_type","PJFNK"}};
 if(kind=="boundary") return {{"boundary","left"},{"value",0.0}};
 return json::object();
}
json catalog() {
 json out=json::array();
 for(auto &[kind,s]: specs) {
  json n={{"kind",kind},{"params",defaults(kind)},{"inputs",json::array()},{"outputs",json::array()}};
  for(auto p:s.inputs) n["inputs"].push_back({{"name",p.name},{"type",p.type}});
  for(auto p:s.outputs) n["outputs"].push_back({{"name",p.name},{"type",p.type}});
  out.push_back(n);
 }
 return out;
}
std::string portType(const std::vector<Port>& ports, const std::string& name) {
 for(auto p:ports) if(p.name==name) return p.type;
 return "";
}
json validate(const json &g) {
 json issues=json::array();
 auto err=[&](std::string code,std::string message,std::string node="") {
  issues.push_back({{"severity","error"},{"code",code},{"message",message},{"node",node}});
 };
 if(!g.is_object() || !g.contains("nodes") || !g["nodes"].is_array() || !g.contains("edges") || !g["edges"].is_array())
  return {{"valid",false},{"issues",json::array({{{"severity","error"},{"code","schema"},{"message","Graph requires nodes and edges arrays."},{"node",""}}})}};
 if(g["nodes"].size()>500 || g["edges"].size()>2000) {
  err("limit","Limit is 500 blocks and 2000 connections."); return {{"valid",false},{"issues",issues}};
 }
 std::unordered_map<std::string,json> nodes;
 std::map<std::string,int> counts, indegree;
 std::map<std::string,std::vector<std::string>> adjacent;
 for(const auto &n:g["nodes"]) {
  if(!n.is_object() || !n.contains("id") || !n["id"].is_string() || !n.contains("kind") || !n["kind"].is_string()
      || !n.contains("params") || !n["params"].is_object()) {err("schema","Each block needs string id/kind and object params.");continue;}
  auto id=n["id"].get<std::string>(), k=n["kind"].get<std::string>();
  if(!std::regex_match(id,std::regex("[A-Za-z_][A-Za-z0-9_]{0,63}"))) {err("id","Block IDs must be safe identifiers.",id);continue;}
  if(nodes.count(id)) {err("duplicate","Duplicate block ID.",id);continue;}
  if(!specs.count(k)) {err("unsupported","Unsupported MOOSE block kind: "+k,id);continue;}
  nodes[id]=n; counts[k]++; indegree[id]=0;
  auto p=n["params"];
  if(k=="mesh") {
   for(auto key:{"dim","nx","ny"}) if(!p.contains(key)||!p[key].is_number_integer()) err("parameter",std::string(key)+" must be an integer.",id);
   if(p.contains("dim") && p["dim"].is_number_integer() && p["dim"]!=1 && p["dim"]!=2) err("parameter","Mesh dimension must be 1 or 2.",id);
   for(auto key:{"nx","ny"}) if(p.contains(key)&&p[key].is_number_integer()&&(p[key]<1 || p[key]>1000)) err("parameter","Mesh counts must be 1–1000.",id);
  }
  if(k=="variable" && (!p.contains("name") || !p["name"].is_string() || !std::regex_match(p["name"].get<std::string>(),std::regex("[A-Za-z_][A-Za-z0-9_]{0,63}")))) err("parameter","Variable name must be a safe identifier.",id);
  if(k=="variable" && p.contains("initial_condition") && (!p["initial_condition"].is_number() || !std::isfinite(p["initial_condition"].get<double>())))
   err("parameter","Initial condition must be a finite constant.",id);
  if(k=="solver") {
   if(p.contains("type") && p["type"]!="Steady" && p["type"]!="Transient")err("parameter","Executioner type must be Steady or Transient.",id);
   if(p.contains("solve_type") && p["solve_type"]!="PJFNK" && p["solve_type"]!="NEWTON" && p["solve_type"]!="JFNK")err("parameter","Unsupported solve_type.",id);
   if(p.contains("scheme") && p["scheme"]!="implicit-euler" && p["scheme"]!="bdf2" && p["scheme"]!="crank-nicolson")err("parameter","Unsupported time integration scheme.",id);
   if(p.value("type",json("Steady"))=="Transient") {
    if(!p.contains("dt") || !p["dt"].is_number() || !std::isfinite(p["dt"].get<double>()) || p["dt"]<=0)err("transient_dt","Transient requires a positive dt.",id);
    if(!p.contains("end_time") && !p.contains("num_steps"))err("transient_end","Transient requires end_time or num_steps.",id);
   } else if(p.contains("dt") || p.contains("end_time") || p.contains("num_steps") || p.contains("scheme"))err("steady_time","Time settings require type = Transient.",id);
   if(p.contains("end_time") && (!p["end_time"].is_number() || !std::isfinite(p["end_time"].get<double>()) || p["end_time"]<=0))err("parameter","end_time must be positive.",id);
   if(p.contains("num_steps") && (!p["num_steps"].is_number_integer() || p["num_steps"]<1 || p["num_steps"]>1000000))err("parameter","num_steps must be an integer from 1 to 1000000.",id);
  }
  for(auto it=p.begin();it!=p.end();++it) if(!editable.at(k).count(it.key()))err("unsupported_parameter","Unsupported parameter: "+it.key(),id);
  if(k=="boundary") {
   if(!p.contains("boundary")||!p["boundary"].is_string()||!std::set<std::string>{"left","right","top","bottom"}.count(p["boundary"].get<std::string>())) err("parameter","Boundary must be left, right, top, or bottom.",id);
   if(!p.contains("value")||!p["value"].is_number()||!std::isfinite(p["value"].get<double>())) err("parameter","Boundary value must be finite.",id);
  }
 }
 for(auto& [sid,sn]:nodes) if(sn["kind"]=="solver" && sn["params"].value("type",json("Steady"))=="Transient")
  for(auto& [vid,vn]:nodes) if(vn["kind"]=="variable" && !vn["params"].contains("initial_condition"))err("initial_condition","Transient diffusion requires an explicit initial_condition on the field.",vid);
 for(auto k:{"mesh","variable","diffusion","solver","output"}) if(counts[k]!=1) err("cardinality",std::string("This diffusion prototype requires exactly one ")+k+" block.");
 if(counts["boundary"]<1) err("boundary","At least one Dirichlet boundary is required.");
 std::set<std::string> seen, boundaryNames;
 std::map<std::pair<std::string,std::string>,int> incoming;
 std::map<std::string,int> outgoing;
 for(const auto &e:g["edges"]) {
  bool shape=e.is_object();
  for(auto key:{"from","out","to","in"}) if(!e.contains(key)||!e[key].is_string()) shape=false;
  if(!shape){err("schema","Connections require string from/out/to/in fields.");continue;}
  std::string a=e["from"],b=e["to"],o=e["out"],i=e["in"];
  if(!nodes.count(a)||!nodes.count(b)){err("dangling","Connection references a missing block.");continue;}
  auto t1=portType(specs.at(nodes[a]["kind"]).outputs,o),t2=portType(specs.at(nodes[b]["kind"]).inputs,i);
  if(t1.empty()||t2.empty()||t1!=t2){err("port","Connection has missing or incompatible ports.",b);continue;}
  if(!seen.insert(a+"."+o+">"+b+"."+i).second){err("duplicate_edge","Duplicate connection.",b);continue;}
  incoming[{b,i}]++; outgoing[a]++; adjacent[a].push_back(b);indegree[b]++;
 }
 for(auto &[id,n]:nodes) {
  std::string k=n["kind"];
  for(auto p:specs.at(k).inputs) {
   int count=incoming[{id,p.name}];
   if(count==0) err("unconnected","Required input '"+p.name+"' is not connected.",id);
   if(count>1 && !(k=="solver"&&p.name=="constraint")) err("multiplicity","Input '"+p.name+"' accepts one connection.",id);
  }
  if(k!="output"&&!outgoing[id]) err("unused","Block has no downstream connection.",id);
  if(k=="boundary"&&n["params"].contains("boundary")&&n["params"]["boundary"].is_string()){
   std::string b=n["params"]["boundary"];
   if(!boundaryNames.insert(b).second) err("conflicting_bc","Multiple conditions on the same boundary.",id);
   for(auto &[mid,m]:nodes) if(m["kind"]=="mesh"&&m["params"].value("dim",0)==1&&(b=="top"||b=="bottom")) err("boundary_dimension","A 1D mesh only has left/right boundaries.",id);
  }
 }
 std::queue<std::string> q;
 for(auto &[id,d]:indegree) if(!d) q.push(id);
 size_t processed=0;
 while(!q.empty()){auto id=q.front();q.pop();processed++;for(auto b:adjacent[id])if(--indegree[b]==0)q.push(b);}
 if(processed!=nodes.size()) err("cycle","Assembly dependencies contain a cycle.");
 return {{"valid",issues.empty()},{"issues",issues},{"nodeCount",nodes.size()},{"edgeCount",g["edges"].size()}};
}
std::string generate(const json& g) {
 json mesh, variable, solver; std::vector<json> boundaries;
 for(auto n:g["nodes"]) {
  if(n["kind"]=="mesh")mesh=n["params"];
  if(n["kind"]=="variable")variable=n["params"];
  if(n["kind"]=="solver")solver=n["params"];
  if(n["kind"]=="boundary")boundaries.push_back(n);
 }
 bool transient=solver.value("type",std::string("Steady"))=="Transient";
 std::ostringstream s;
 s << "# Generated by VIBORA: " << (transient?"transient":"steady") << " unit-coefficient diffusion\n"
   << "[Mesh]\n  type = GeneratedMesh\n  dim = " << mesh["dim"] << "\n  nx = " << mesh["nx"] << "\n";
 if(mesh["dim"]==2)s<<"  ny = "<<mesh["ny"]<<"\n";
 std::string u=variable["name"];
 s<<"[]\n\n[Variables]\n  ["<<u<<"]\n    order = FIRST\n    family = LAGRANGE\n";
 if(variable.contains("initial_condition"))s<<"    initial_condition = "<<variable["initial_condition"]<<"\n";
 s<<"  []\n[]\n\n[Kernels]\n  [diffusion]\n    type = Diffusion\n    variable = "<<u<<"\n  []\n";
 if(transient)s<<"  [time_derivative]\n    type = TimeDerivative\n    variable = "<<u<<"\n  []\n";
 s<<"[]\n\n[BCs]\n";
 for(auto n:boundaries)s<<"  ["<<n["id"].get<std::string>()<<"]\n    type = DirichletBC\n    variable = "<<u<<"\n    boundary = "<<n["params"]["boundary"].get<std::string>()<<"\n    value = "<<n["params"]["value"]<<"\n  []\n";
 s<<"[]\n\n[Executioner]\n  type = "<<(transient?"Transient":"Steady")<<"\n  solve_type = "<<solver.value("solve_type",std::string("PJFNK"))<<"\n";
 if(transient) {
  s<<"  dt = "<<solver["dt"]<<"\n";
  for(auto key:{"end_time","num_steps"})if(solver.contains(key))s<<"  "<<key<<" = "<<solver[key]<<"\n";
  s<<"  scheme = "<<solver.value("scheme",std::string("implicit-euler"))<<"\n";
 }
 s<<"[]\n\n[Outputs]\n  exodus = true\n[]\n";
 return s.str();
}
json compile_graph(const json& g) {
 auto result=validate(g);
 // Resolve intent before final physical validation: descriptions may supply missing parameters.
 // Schema and topology errors still block generation.
 if(!result["valid"].get<bool>()) {
  for(const auto& i:result["issues"]) {
   std::string code=i["code"];
   if(code!="transient_dt" && code!="transient_end" && code!="initial_condition" && code!="steady_time" && code!="parameter")return result;
  }
 }
 json resolved=g;
 if(has_intent(g)) {
  try {
   auto plan=resolve_intent(g);
   result["changes"]=plan["changes"];result["summary"]=plan["summary"];
   if(!plan["unresolved"].empty()) {
    result["valid"]=false;result["issues"]=json::array();
    for(auto& question:plan["unresolved"])result["issues"].push_back({{"severity","error"},{"code","unresolved_intent"},{"message",question},{"node",""}});
    return result;
   }
   resolved=plan["graph"];
  }catch(const std::exception& e) {
   result["valid"]=false;result["issues"]=json::array({{{"severity","error"},{"code","agent"},{"message",e.what()},{"node",""}}});return result;
  }
 }
 auto checked=validate(resolved);
 result["valid"]=checked["valid"];result["issues"]=checked["issues"];
 if(result["valid"].get<bool>()) {
  result["resolvedGraph"]=resolved;
  result["input"]=generate(resolved);
  result["summary"]=result.value("summary",std::string("Generated from explicit block parameters."));
  result["changes"]=result.value("changes",json::array());
 }
 return result;
}
int main(int argc,char**argv) {
 if(argc>1&&std::string(argv[1])=="--generate"){
  try {json g;std::cin>>g;auto result=compile_graph(g);if(!result["valid"].get<bool>()){std::cerr<<result.dump(2)<<"\n";return 1;}std::cout<<result["input"].get<std::string>();return 0;}
  catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}
 }
 int port=8080;std::string root="web";
 if(argc>1) port=std::stoi(argv[1]);
 if(argc>2) root=argv[2];
 httplib::Server server;
 // httplib's default SO_REUSEPORT lets a stale server silently share the port and answer
 // with another session's token; plain SO_REUSEADDR makes a second server fail to bind.
 server.set_socket_options([](socket_t sock){int yes=1;setsockopt(sock,SOL_SOCKET,SO_REUSEADDR,reinterpret_cast<const void*>(&yes),sizeof(yes));});
 // Under the laptop bridge, stdin stays open for the SSH session; EOF means the bridge is gone.
 if(std::getenv("VIBORA_EXIT_ON_EOF"))std::thread([]{std::string line;while(std::getline(std::cin,line)){}std::cerr<<"Bridge disconnected; stopping.\n";std::_Exit(0);}).detach();
 register_workflow(server);
 server.new_task_queue=[] { return new httplib::ThreadPool(4); };
 server.set_payload_max_length(1024*1024);
 server.set_read_timeout(10,0);server.set_write_timeout(310,0);
 server.Get("/api/catalog",[](const auto&,auto&r){r.set_content(catalog().dump(),"application/json");});
 auto action=[](bool gen,const httplib::Request&req,httplib::Response&r){
  try {
   auto g=json::parse(req.body);auto result=gen?compile_graph(g):validate(g);
   r.status=result["valid"].get<bool>()?200:422;
   r.set_content(result.dump(),"application/json");
  }catch(const std::exception&){r.status=400;r.set_content(R"({"valid":false,"issues":[{"message":"Malformed graph or parameter type.","severity":"error","code":"schema"}]})","application/json");}
 };
 server.Post("/api/validate",[&](auto&req,auto&r){action(false,req,r);});
 server.Post("/api/generate",[&](auto&req,auto&r){action(true,req,r);});
 server.set_default_headers({{"X-Content-Type-Options","nosniff"},{"Cache-Control","no-store"}});
 if(!server.set_mount_point("/",root)){std::cerr<<"Web directory not found: "<<root<<"\n";return 1;}
 std::cout<<"VIBORA http://127.0.0.1:"<<port<<std::endl;
 if(!server.listen("127.0.0.1",port)){std::cerr<<"Cannot bind port\n";return 1;}
}
