#if UNITY_EDITOR
using System;
using System.IO;
using System.Net;
using System.Text;
using System.Collections;
using System.Collections.Generic;
using System.Threading;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public class UnityMcpBridge
{
    private static HttpListener listener;
    private static bool isRunning = false;
    private static readonly int[] PORTS = new int[] { 8090, 8091, 8092, 8093, 8094, 8095 };
    public static int ActivePort { get; private set; } = 8090;

    private static readonly Queue<Action> mainThreadQueue = new Queue<Action>();
    private static readonly List<string> consoleLogs = new List<string>();

    static UnityMcpBridge()
    {
        Application.runInBackground = true;
        EditorApplication.update += UpdateMainThread;
        Application.logMessageReceived += HandleLog;
        AssemblyReloadEvents.beforeAssemblyReload += StopServer;
        EditorApplication.quitting += StopServer;
        EditorApplication.playModeStateChanged += (change) =>
        {
            if (change == PlayModeStateChange.ExitingEditMode || change == PlayModeStateChange.ExitingPlayMode)
            {
                StopServer();
            }
            else if (change == PlayModeStateChange.EnteredPlayMode || change == PlayModeStateChange.EnteredEditMode)
            {
                EditorApplication.delayCall += StartServer;
            }
        };
        EditorApplication.delayCall += StartServer;
    }

    private static void HandleLog(string logString, string stackTrace, LogType type)
    {
        lock (consoleLogs)
        {
            if (consoleLogs.Count > 100) consoleLogs.RemoveAt(0);
            consoleLogs.Add($"[{type}] {logString}");
        }
    }

    [MenuItem("Tools/MCP/Restart Bridge")]
    public static void RestartServerMenu()
    {
        StopServer();
        Thread.Sleep(100);
        StartServer();
    }

    [MenuItem("Tools/MCP/Ping Test")]
    public static void PingTestMenu()
    {
        Debug.Log($"[Unity MCP Bridge] Status: isRunning={isRunning}, port={ActivePort}, listener.IsListening={listener?.IsListening}");
    }

    private static void StartServer()
    {
        if (isRunning && listener != null && listener.IsListening) return;
        StopServer();

        foreach (int port in PORTS)
        {
            try
            {
                listener = new HttpListener();
                listener.Prefixes.Add($"http://127.0.0.1:{port}/");
                listener.Start();
                isRunning = true;
                ActivePort = port;
                listener.BeginGetContext(OnContextReceived, listener);
                Debug.Log($"<color=#15803d><b>[Unity MCP Bridge]</b></color> Active on http://127.0.0.1:{port}/");
                return;
            }
            catch
            {
                try { listener?.Close(); } catch { }
                listener = null;
            }
        }

        Debug.LogWarning("[Unity MCP Bridge] Could not bind to any port in range 8090-8095.");
    }

    private static void OnContextReceived(IAsyncResult ar)
    {
        var l = ar.AsyncState as HttpListener;
        if (l == null || !l.IsListening) return;

        try
        {
            var context = l.EndGetContext(ar);
            l.BeginGetContext(OnContextReceived, l);
            ProcessRequest(context);
        }
        catch { }
    }

    private static void StopServer()
    {
        isRunning = false;
        try
        {
            if (listener != null)
            {
                if (listener.IsListening) listener.Stop();
                listener.Close();
                listener = null;
            }
        }
        catch { }
    }

    private static void ProcessRequest(HttpListenerContext context)
    {
        string path = context.Request.Url.AbsolutePath;
        string body = "";
        using (var reader = new StreamReader(context.Request.InputStream, context.Request.ContentEncoding))
        {
            body = reader.ReadToEnd();
        }

        var responsePayload = new Dictionary<string, object>();

        if (path == "/unity_ping")
        {
            responsePayload["success"] = true;
            responsePayload["message"] = "Unity Editor is online and connected to MCP!";
            responsePayload["unity_version"] = Application.unityVersion;
            responsePayload["project_path"] = Application.dataPath;
            SendResponse(context, responsePayload);
            return;
        }

        var resetEvent = new ManualResetEvent(false);
        lock (mainThreadQueue)
        {
            mainThreadQueue.Enqueue(() =>
            {
                try
                {
                    switch (path)
                    {
                        case "/unity_build_stylized_street":
                            StreetTycoon.Editor.StylizedStreetBuilder.BuildStylizedStreetScene();
                            responsePayload["success"] = true;
                            responsePayload["message"] = "High-Quality Stylized Street constructed successfully.";
                            break;

                        case "/unity_setup_gameflow":
                            StreetTycoon.Editor.CreatePlayableGameFlow.BuildPlayableGameFlow();
                            responsePayload["success"] = true;
                            responsePayload["message"] = "Playable Game Flow (Start Menu + Tutorial + Gameplay + Camera) configured successfully.";
                            break;

                        case "/unity_setup_phase6":
                            StreetTycoon.Editor.CreatePhase6Unlock.BuildPhase6Scene();
                            responsePayload["success"] = true;
                            responsePayload["message"] = "Phase 6 Snack Cart Unlock System configured successfully.";
                            break;

                        case "/unity_setup_phase5":
                            StreetTycoon.Editor.CreatePhase5Polish.BuildPhase5Scene();
                            responsePayload["success"] = true;
                            responsePayload["message"] = "Phase 5 Polished UI & Business Panel configured successfully.";
                            break;

                        case "/unity_setup_phase4":
                            StreetTycoon.Editor.CreatePhase4Setup.BuildPhase4Scene();
                            responsePayload["success"] = true;
                            responsePayload["message"] = "Phase 4 Tea Stall Gameplay & UI configured successfully.";
                            break;

                        case "/unity_setup_phase3":
                            StreetTycoon.Editor.CreatePhase3Economy.CreateEconomyAssets();
                            responsePayload["success"] = true;
                            responsePayload["message"] = "Phase 3 Economy Assets (SO_TeaStall) created successfully.";
                            break;

                        case "/unity_build_phase2":
                            StreetTycoon.Editor.CreatePhase2Street.BuildStreetScene();
                            responsePayload["success"] = true;
                            responsePayload["message"] = "Phase 2 Street Prototype built successfully.";
                            break;

                        case "/unity_setup_phase1":
                            StreetTycoon.Editor.CreatePhase1Scenes.BuildPhase1Scenes();
                            responsePayload["success"] = true;
                            responsePayload["message"] = "Phase 1 Scenes (Bootstrap & Main) created and configured.";
                            break;

                        case "/unity_refresh_assets":
                            AssetDatabase.Refresh();
                            responsePayload["success"] = true;
                            responsePayload["message"] = "AssetDatabase refreshed.";
                            break;

                        case "/unity_get_hierarchy":
                            var rootObjs = UnityEngine.SceneManagement.SceneManager.GetActiveScene().GetRootGameObjects();
                            var hierarchyList = new List<Dictionary<string, object>>();
                            foreach (var go in rootObjs)
                            {
                                hierarchyList.Add(GetGameObjectTree(go));
                            }
                            responsePayload["success"] = true;
                            responsePayload["hierarchy"] = hierarchyList;
                            break;

                        case "/unity_create_gameobject":
                            var createData = JsonUtility.FromJson<CreateObjectParams>(body);
                            GameObject newObj = null;

                            if (createData.primitive_type == "Cube") newObj = GameObject.CreatePrimitive(PrimitiveType.Cube);
                            else if (createData.primitive_type == "Sphere") newObj = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                            else if (createData.primitive_type == "Capsule") newObj = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                            else if (createData.primitive_type == "Cylinder") newObj = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                            else if (createData.primitive_type == "Plane") newObj = GameObject.CreatePrimitive(PrimitiveType.Plane);
                            else newObj = new GameObject(createData.name ?? "New GameObject");

                            if (newObj != null)
                            {
                                newObj.name = createData.name ?? newObj.name;
                                if (createData.position != null) newObj.transform.position = createData.position.ToVector3();
                                if (createData.rotation != null) newObj.transform.eulerAngles = createData.rotation.ToVector3();
                                if (createData.scale != null) newObj.transform.localScale = createData.scale.ToVector3();

                                Undo.RegisterCreatedObjectUndo(newObj, "Create " + newObj.name);
                                Selection.activeGameObject = newObj;

                                responsePayload["success"] = true;
                                responsePayload["game_object_id"] = newObj.GetHashCode();
                                responsePayload["name"] = newObj.name;
                            }
                            break;

                        case "/unity_add_component":
                            var compData = JsonUtility.FromJson<AddComponentParams>(body);
                            var targetGo = GameObject.Find(compData.game_object_name);
                            if (targetGo != null)
                            {
                                var assemblies = AppDomain.CurrentDomain.GetAssemblies();
                                Type foundType = null;
                                foreach (var asm in assemblies)
                                {
                                    try
                                    {
                                        foreach (var t in asm.GetTypes())
                                        {
                                            if (t.Name == compData.component_name)
                                            {
                                                foundType = t;
                                                break;
                                            }
                                        }
                                    }
                                    catch { }
                                    if (foundType != null) break;
                                }

                                if (foundType != null)
                                {
                                    var comp = Undo.AddComponent(targetGo, foundType);
                                    responsePayload["success"] = true;
                                    responsePayload["message"] = $"Added component {compData.component_name} to {targetGo.name}";
                                }
                                else
                                {
                                    responsePayload["success"] = false;
                                    responsePayload["error"] = $"Component type '{compData.component_name}' not found.";
                                }
                            }
                            else
                            {
                                responsePayload["success"] = false;
                                responsePayload["error"] = $"GameObject '{compData.game_object_name}' not found.";
                            }
                            break;

                        case "/unity_set_play_mode":
                            var playData = JsonUtility.FromJson<PlayModeParams>(body);
                            if (playData.state == "play") EditorApplication.isPlaying = true;
                            else if (playData.state == "stop") EditorApplication.isPlaying = false;
                            else if (playData.state == "pause") EditorApplication.isPaused = !EditorApplication.isPaused;
                            responsePayload["success"] = true;
                            responsePayload["isPlaying"] = EditorApplication.isPlaying;
                            break;

                        case "/unity_get_console_logs":
                            lock (consoleLogs)
                            {
                                responsePayload["success"] = true;
                                responsePayload["logs"] = new List<string>(consoleLogs);
                            }
                            break;

                        default:
                            responsePayload["success"] = false;
                            responsePayload["error"] = "Unknown MCP endpoint: " + path;
                            break;
                    }
                }
                catch (Exception ex)
                {
                    responsePayload["success"] = false;
                    responsePayload["error"] = ex.Message;
                }
                finally
                {
                    resetEvent.Set();
                }
            });
        }

        resetEvent.WaitOne(5000);

        SendResponse(context, responsePayload);
    }

    private static void SendResponse(HttpListenerContext context, Dictionary<string, object> payload)
    {
        try
        {
            string jsonResponse = MiniJsonSerializer(payload);
            byte[] buffer = Encoding.UTF8.GetBytes(jsonResponse);
            context.Response.ContentType = "application/json";
            context.Response.ContentLength64 = buffer.Length;
            context.Response.OutputStream.Write(buffer, 0, buffer.Length);
            context.Response.OutputStream.Close();
        }
        catch { }
    }

    private static void UpdateMainThread()
    {
        lock (mainThreadQueue)
        {
            while (mainThreadQueue.Count > 0)
            {
                mainThreadQueue.Dequeue()?.Invoke();
            }
        }
    }

    private static Dictionary<string, object> GetGameObjectTree(GameObject go)
    {
        var dict = new Dictionary<string, object>
        {
            ["id"] = go.GetHashCode(),
            ["name"] = go.name,
            ["active"] = go.activeSelf,
            ["tag"] = go.tag,
            ["position"] = new float[] { go.transform.position.x, go.transform.position.y, go.transform.position.z }
        };

        var children = new List<Dictionary<string, object>>();
        for (int i = 0; i < go.transform.childCount; i++)
        {
            children.Add(GetGameObjectTree(go.transform.GetChild(i).gameObject));
        }
        dict["children"] = children;
        return dict;
    }

    private static string MiniJsonSerializer(Dictionary<string, object> dict)
    {
        var sb = new StringBuilder("{");
        bool first = true;
        foreach (var kvp in dict)
        {
            if (!first) sb.Append(",");
            first = false;
            sb.Append($"\"{kvp.Key}\":");
            if (kvp.Value is string s) sb.Append($"\"{EscapeString(s)}\"");
            else if (kvp.Value is bool b) sb.Append(b ? "true" : "false");
            else if (kvp.Value is int || kvp.Value is float || kvp.Value is double) sb.Append(kvp.Value.ToString());
            else if (kvp.Value is IEnumerable<string> strList)
            {
                sb.Append("[");
                bool lFirst = true;
                foreach (var item in strList)
                {
                    if (!lFirst) sb.Append(",");
                    lFirst = false;
                    sb.Append($"\"{EscapeString(item)}\"");
                }
                sb.Append("]");
            }
            else sb.Append($"\"{EscapeString(kvp.Value?.ToString() ?? "")}\"");
        }
        sb.Append("}");
        return sb.ToString();
    }

    private static string EscapeString(string str) => str.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "");

    [Serializable] public class Vector3Data { public float x, y, z; public Vector3 ToVector3() => new Vector3(x, y, z); }
    [Serializable] public class CreateObjectParams { public string name; public string primitive_type; public Vector3Data position; public Vector3Data rotation; public Vector3Data scale; }
    [Serializable] public class AddComponentParams { public string game_object_name; public string component_name; }
    [Serializable] public class PlayModeParams { public string state; }
}
#endif
