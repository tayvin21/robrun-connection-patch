// Fix 1: NetworkPeer.Connect gets a hard 2.5 s deadline, independent of ping

public partial class NetworkPeer
{
    private const int ConnectTimeoutMs = 2500;
    public const int ConnectTimeoutError = -2;
    private long _connectTimeoutAt;

    public IAwaiter<IEither<int, Unit>> Connect(IPAddress address, int port, int startRtt)
    {
        _connectDeferred = CreateDeferred<IEither<int, Unit>>();
        _connectTimeoutAt = _now.Milliseconds + ConnectTimeoutMs;
        _peer.Connect(address, port, startRtt);
        return _connectDeferred.Awaiter;
    }

    private void CheckConnectTimeout()   // call alongside the existing request-timeout check
    {
        if (_connectDeferred == null || _now.Milliseconds < _connectTimeoutAt) return;
        var deferred = _connectDeferred;
        _connectDeferred = null;
        _peer.DisconnectNow();
        deferred.Resolve(Left<int, Unit>(ConnectTimeoutError));
    }
}


// Fix 2 + 3: ConnectUpdater stops after 2 failures on the same assignment and drops stale attempts

public abstract partial class ConnectUpdater
{
    private const int MaxFailuresPerAssignment = 2;

    private string _assignment;
    private int _assignmentVersion;
    private int _failures;
    private bool _gaveUp;

    public void Update()
    {
        var target = _connectionInfo.Host == null
            ? null
            : _connectionInfo.Host + ":" + _connectionInfo.Port + ":" + _connectionInfo.Destination;

        if (target != _assignment)
        {
            _assignment = target;
            _assignmentVersion++;
            _failures = 0;
            _gaveUp = false;
        }

        if (!NeedConnect)
            return;

        if (_failures >= MaxFailuresPerAssignment)
        {
            if (!_gaveUp)
            {
                _gaveUp = true;
                OnTargetUnreachable();
            }
            return;
        }

        Connect(_assignmentVersion);
    }

    private async void Connect(int version)
    {
        // ... existing DNS / ping / StartHost steps ...

        var result = await ConnectInternal(/* existing arguments */);

        if (version != _assignmentVersion)
        {
            _peerConnection.DisconnectNow();
            return;
        }

        if (result.IsLeft)
            _failures++;

        // ... existing success / failure logging ...
    }

    protected virtual void OnTargetUnreachable() { }
}


// Fix 2 (battle connection): tell the region server instead of waiting out its 60 s timeout

public partial class BattleConnectionUpdater : ConnectUpdater
{
    protected override void OnTargetUnreachable()
    {
        regionUserConnection.SendMessage(new BattleConnectFailedMessage(
            _connectionInfo.Destination,
            _connectionInfo.Host,
            _connectionInfo.Port));
    }
}


// Fix 4: retry PeerAuthorize on "timeout" as well as "already_connected"

Func<IValue, bool> retryAuthorize = response =>
    isNetworkHostStarted && isConnected && authorizeAttempts > 0
    && (response == "already_connected" || response == "timeout");


// Server side: on BattleConnectFailedMessage

void OnBattleConnectFailed(Player player, BattleConnectFailedMessage msg)
{
    if (player.IsAuthorizedOn(msg.Destination))
        return;                                         // late success won the race, ignore

    CancelPendingJoin(player, msg.Destination);         // same path the 60 s timeout uses today
    MarkConnectFailure(msg.Host);                       // drain the server after K failures in a short window
    AssignBattle(player, exclude: msg.Host);            // send them somewhere that works
}
