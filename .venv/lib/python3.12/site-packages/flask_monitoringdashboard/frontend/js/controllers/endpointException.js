export function EndpointExceptionController(
    $scope,
    $http,
    menuService,
    paginationService,
    endpointService,
) {
    Prism.plugins.NormalizeWhitespace.setDefaults({
        "remove-trailing": false,
        "remove-indent": false,
        "left-trim": true,
        "right-trim": true,
    });

    endpointService.reset();
    menuService.reset("endpoint_exception");
    $scope.id2Function = {};
    $scope.idHasBeenClicked = {};

    $scope.table = [];

    endpointService.onNameChanged = function (name) {
        $scope.title = "Exceptions for " + name;
    };

    paginationService.init("exceptions");
    $http.get("api/num_exceptions/" + endpointService.info.id).then(
        function (response) {
            paginationService.setTotal(response.data);
        },
    );

    paginationService.onReload = function () {
        $http.get(
            "api/detailed_exception_occurrence/" + endpointService.info.id + "/" +
            paginationService.getLeft() + "/" + paginationService.perPage,
        )
            .then(function (response) {
                $scope.table = response.data;
                $scope.id2Function = {};
                $scope.idHasBeenClicked = {};
            });
    };

    $scope.getUniqueKey = function (stack_trace_snapshot_id, stack_trace_position) {
        return `code_${stack_trace_snapshot_id}_${stack_trace_position}`; // the stack_trace_position is important when dealing with recursive functions
    };

    $scope.loadFunctionCodeById = function (function_definition_id, key) {
        if ($scope.id2Function[function_definition_id] === undefined) {
            $http.get(`api/function_code/${function_definition_id}`)
                .then((response) => {
                    $scope.id2Function[function_definition_id] = response.data;
                    $scope.idHasBeenClicked[key] = true; // important that only marked after data has been fetched
                });
        } else {
            $scope.idHasBeenClicked[key] = true;
        }
    };

    $scope.highlightCode = function (key) {
        $scope.$applyAsync(() => {
          const element = document.getElementById(key);
          if (element) {
            Prism.highlightElement(element);
          }
        });
    };

    $scope.deleteExceptionByStackTraceId = function (stack_trace_snapshot_id) {
        if (
            stack_trace_snapshot_id &&
            confirm("Are you sure you want to delete exception?")
        ) {
            $http.delete(`api/exception_occurrence/${stack_trace_snapshot_id}`)
                .then((_) => {
                    paginationService.onReload();
                    paginationService.total--;
                });
        }
    };

    $scope.collapseDetailsByStackTraceId = function (stack_trace_snapshot_id) {
        document.querySelectorAll(`#details_${stack_trace_snapshot_id}`).forEach((details) => {
            details.open = false;
        });
    };
}
