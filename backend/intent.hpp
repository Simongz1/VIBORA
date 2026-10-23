// Description-to-configuration boundary. Agent output is data, never executable code.
bool has_intent(const json& g) {
 for(const auto& n:g.at("nodes")) {
  for(auto key:{"physics","method","implementation"})
   if(n.contains(key) && n[key].is_string() && !n[key].get<std::string>().empty()) return true;
  if(n.value("kind","")=="solver") {
   std::string label=n.value("label","");std::transform(label.begin(),label.end(),label.begin(),::tolower);
   if(label.find("transient")!=std::string::npos) return true;
  }
 }
 return false;
}
const std::map<std::string,std::set<std::string>> editable = {
 {"mesh",{"dim","nx","ny"}}, {"variable",{"name","initial_condition"}},
 {"diffusion",{}}, {"boundary",{"boundary","value"}},
 {"solver",{"type","dt","end_time","num_steps","scheme","solve_type"}}, {"output",{}}
};
json resolve_intent(const json& g) {
 const char* port=std::getenv("VIBORA_AGENT_PORT");
 if(!port) throw std::runtime_error("Coding agent is offline. Start scripts/agent_bridge.py (see docs/SETUP.md).");
 httplib::Client agent("127.0.0.1",std::stoi(port));
 agent.set_connection_timeout(3);agent.set_read_timeout(300);agent.set_write_timeout(10);
 httplib::Headers headers;
 if(const char* token=std::getenv("VIBORA_AGENT_TOKEN"))headers.emplace("Authorization",std::string("Bearer ")+token);
 auto response=agent.Post("/resolve",headers,g.dump(),"application/json");
 if(!response)throw std::runtime_error("Coding agent could not be reached or timed out. Check the bridge and Codex login.");
 if(response->status!=200)throw std::runtime_error("Coding agent failed: "+response->body.substr(0,1000));
 json plan=json::parse(response->body);
 if(!plan.is_object()||!plan.contains("patches")||!plan["patches"].is_array()||!plan.contains("unresolved")||!plan["unresolved"].is_array()||!plan.contains("summary")||!plan["summary"].is_string())
  throw std::runtime_error("Coding agent returned an invalid plan.");
 json resolved=g, changes=json::array();
 std::set<std::pair<std::string,std::string>> touched;
 for(const auto& patch:plan["patches"]) {
  std::string id=patch.at("node"),key=patch.at("key"),encoded=patch.at("value"),reason=patch.at("reason");
  auto found=std::find_if(resolved["nodes"].begin(),resolved["nodes"].end(),[&](const json& n){return n["id"]==id;});
  if(found==resolved["nodes"].end())throw std::runtime_error("Agent referenced an unknown block.");
  if(!editable.at((*found)["kind"]).count(key))throw std::runtime_error("Unsupported agent parameter: "+key);
  if(!touched.insert({id,key}).second)throw std::runtime_error("Agent proposed conflicting changes.");
  json value=json::parse(encoded), before=(*found)["params"].value(key,json(nullptr));
  if(value.is_null()) (*found)["params"].erase(key);
  else (*found)["params"][key]=value;
  changes.push_back({{"node",id},{"key",key},{"before",before},{"after",value},{"reason",reason}});
 }
 return {{"graph",resolved},{"changes",changes},{"summary",plan["summary"]},{"unresolved",plan["unresolved"]}};
}
